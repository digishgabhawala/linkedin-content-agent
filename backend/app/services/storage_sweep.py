"""Classification for the one-off Supabase Storage sweep."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Character, HeroCandidate, HeroGenerationRun


@dataclass
class StoredObject:
    bucket: str
    path: str
    size: int
    created_at: datetime


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _public_url(obj: StoredObject) -> str:
    base = settings.supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/public/{obj.bucket}/{quote(obj.path, safe='/')}"


def classify(
        objects: list[StoredObject], *, keep_urls: set[str], keep_paths: set[str],
        now: datetime, artifacts_before: datetime | None) -> list[StoredObject]:
    """Return objects safe to delete, preserving recent or referenced files."""
    recent_after = _utc_naive(now) - timedelta(days=7)
    cutoff = _utc_naive(artifacts_before) if artifacts_before is not None else None
    normalized_urls = {_without_query(url) for url in keep_urls if url}
    deletions = []
    for obj in objects:
        created_at = _utc_naive(obj.created_at)
        if created_at > recent_after:
            continue
        if obj.bucket == "linkedin":
            if not obj.path.startswith("characters/") or obj.path in keep_paths:
                continue
            deletions.append(obj)
        elif obj.bucket == "artifacts":
            if cutoff is None or created_at >= cutoff:
                continue
            if _without_query(_public_url(obj)) not in normalized_urls:
                deletions.append(obj)
    return deletions


def discard_stale_candidates(db: Session) -> int:
    """Discard ready candidates older than their character's selected hero."""
    count = 0
    characters = db.scalars(select(Character).where(
        Character.hero_candidate_id.is_not(None)
    )).all()
    for character in characters:
        selected = db.get(HeroCandidate, character.hero_candidate_id)
        if selected is None or selected.selected_at is None:
            continue
        belongs_to_character = db.scalar(select(HeroGenerationRun.id).where(
            HeroGenerationRun.id == selected.run_id,
            HeroGenerationRun.character_id == character.character_id,
        ))
        if belongs_to_character is None:
            continue
        stale = db.scalars(
            select(HeroCandidate)
            .join(HeroGenerationRun)
            .where(
                HeroGenerationRun.character_id == character.character_id,
                HeroCandidate.id != selected.id,
                HeroCandidate.status == "ready",
                HeroCandidate.created_at < selected.selected_at,
            )
        ).all()
        for candidate in stale:
            candidate.status = "discarded"
        count += len(stale)
    return count
