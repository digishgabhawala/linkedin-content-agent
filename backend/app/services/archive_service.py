"""Archive and restore posts without making image cleanup user-blocking."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ImageDeletion, Post
from . import image_cleanup


class PostBusy(Exception):
    """The post cannot be archived while work is still in flight."""


def archive_post(
        db: Session, post: Post, *, now: datetime | None = None) -> list[ImageDeletion]:
    if post.archived_at is not None:
        return []
    if post.active_step or post.status == "image_queued":
        raise PostBusy(f"post {post.id} is busy with a step -- wait for it to finish")

    deletion = image_cleanup.queue_post_image(db, post, "archived")
    post.archived_at = now or datetime.utcnow()
    post.final_image_path = None
    post.image_task_id = None
    post.image_job_error = None
    db.commit()
    db.refresh(post)
    return [deletion] if deletion is not None else []


def unarchive_post(db: Session, post: Post) -> Post:
    post.archived_at = None
    if post.status in ("image_ready", "image_failed", "ready"):
        post.status = "locked"
    db.commit()
    db.refresh(post)
    return post


def auto_archive_date(post: Post, *, days: int) -> datetime | None:
    if days == 0 or post.archived_at is not None or post.updated_at is None:
        return None
    return post.updated_at + timedelta(days=days)


async def auto_archive(
        db: Session, queue_client, *, now: datetime, days: int,
        limit: int = 50) -> int:
    if days == 0:
        return 0

    posts = list(db.scalars(
        select(Post).where(
            Post.archived_at.is_(None),
            Post.updated_at < now - timedelta(days=days),
            Post.active_step.is_(None),
            Post.status != "image_queued",
        ).order_by(Post.updated_at).limit(limit)
    ))
    for post in posts:
        rows = archive_post(db, post, now=now)
        await image_cleanup.attempt(db, rows, queue_client=queue_client)
    return len(posts)
