"""Best-effort deletion outbox for post renders and character images."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import ImageDeletion, Post
from . import llm_client


_ARTIFACT_PATH = re.compile(
    r"^/storage/v1/object/public/artifacts/"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.(?:png|webp|jpg)$"
)


def _same_supabase_host(url: str) -> bool:
    try:
        expected = urlsplit(settings.supabase_url).hostname
        actual = urlsplit(url).hostname
    except ValueError:
        return False
    return bool(expected and actual and expected == actual)


def artifact_id_from_url(url: str | None) -> str | None:
    if not url or not _same_supabase_host(url):
        return None
    match = _ARTIFACT_PATH.fullmatch(urlsplit(url).path)
    if match is None:
        return None
    try:
        return str(uuid.UUID(match.group(1)))
    except ValueError:
        return None


def storage_path_from_url(url: str | None) -> str | None:
    if not url or not _same_supabase_host(url):
        return None
    prefix = f"/storage/v1/object/public/{settings.storage_bucket}/"
    path = urlsplit(url).path
    if not path.startswith(prefix):
        return None
    object_path = path.removeprefix(prefix)
    if not object_path or object_path.startswith("/"):
        return None
    return object_path


def queue_post_image(db: Session, post: Post, reason: str) -> ImageDeletion | None:
    artifact_id = artifact_id_from_url(post.final_image_path)
    if artifact_id is None:
        return None
    row = ImageDeletion(
        owner_id=post.owner_id,
        location="queue_artifact",
        ref=artifact_id,
        reason=reason,
        post_id=post.id,
    )
    db.add(row)
    return row


def queue_storage_object(
        db: Session, *, owner_id: str, path: str, reason: str,
        character_id: str | None = None,
        not_before: datetime | None = None) -> ImageDeletion | None:
    if not path.startswith(f"characters/{owner_id}/"):
        return None
    row = ImageDeletion(
        owner_id=owner_id,
        location="linkedin_storage",
        ref=path,
        reason=reason,
        character_id=character_id,
        not_before=not_before,
    )
    db.add(row)
    return row


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _delete_storage(
        client: httpx.AsyncClient, row: ImageDeletion,
        storage_auth: tuple[str, str]) -> None:
    bearer, apikey = storage_auth
    base = settings.supabase_url.rstrip("/")
    response = await client.delete(
        f"{base}/storage/v1/object/{settings.storage_bucket}/{row.ref}",
        headers={"Authorization": f"Bearer {bearer}", "apikey": apikey},
        timeout=15,
    )
    if response.status_code in (400, 404):
        return
    response.raise_for_status()


async def attempt(
        db: Session, rows: list[ImageDeletion], *,
        queue_client: httpx.AsyncClient | None = None,
        storage_client: httpx.AsyncClient | None = None,
        storage_auth: tuple[str, str] | None = None) -> None:
    now = datetime.utcnow()
    for row in rows:
        if row.deleted_at is not None:
            continue
        if row.not_before is not None and _utc_naive(row.not_before) > now:
            continue
        if (row.reason == "candidate_unpicked" and row.not_before is not None
                and row.character_id is not None
                and db.scalar(select(Post.id).where(
                    Post.owner_id == row.owner_id,
                    Post.character_id == row.character_id,
                    Post.status == "image_queued",
                ).limit(1)) is not None):
            continue
        if row.location == "queue_artifact" and queue_client is None:
            continue
        if row.location == "linkedin_storage" and (
                storage_client is None or storage_auth is None):
            continue
        try:
            if row.location == "queue_artifact":
                await llm_client.delete_artifact(queue_client, row.ref)
            elif row.location == "linkedin_storage":
                await _delete_storage(storage_client, row, storage_auth)
            else:
                raise ValueError(f"unknown image deletion location: {row.location}")
            row.deleted_at = datetime.utcnow()
            row.last_error = None
        except Exception as exc:  # noqa: BLE001 -- deletion is always best effort
            row.attempts = (row.attempts or 0) + 1
            row.last_error = str(exc)[:500]
    try:
        db.commit()
    except Exception:  # noqa: BLE001 -- cleanup must not fail the user's request
        db.rollback()


def pending(
        db: Session, *, location: str, owner_id: str | None = None,
        limit: int = 100) -> list[ImageDeletion]:
    statement = select(ImageDeletion).where(
        ImageDeletion.location == location,
        ImageDeletion.deleted_at.is_(None),
    )
    if owner_id is not None:
        statement = statement.where(ImageDeletion.owner_id == owner_id)
    statement = statement.order_by(ImageDeletion.created_at).limit(limit)
    return list(db.scalars(statement))


def prune_done(
        db: Session, *, now: datetime, older_than_days: int = 30,
        limit: int = 500) -> int:
    cutoff = _utc_naive(now) - timedelta(days=older_than_days)
    statement = select(ImageDeletion).where(
        ImageDeletion.deleted_at.is_not(None),
        ImageDeletion.deleted_at < cutoff,
    ).order_by(ImageDeletion.deleted_at).limit(limit)
    rows = list(db.scalars(statement))
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)
