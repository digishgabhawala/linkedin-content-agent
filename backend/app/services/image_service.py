"""image_service.py -- spawns character-forge-v2 as a detached subprocess and
receives its completion callback.

Never imports forge2 -- shells out via subprocess.Popen only, per this
workspace's "each tool is a standalone sibling directory, shares nothing"
convention. Popen returns instantly (fire-and-forget); the forge2 subprocess
POSTs back to /api/internal/image-callback when it finishes (see
character-forge-v2/forge2/stages/generate.py's callback_url support).

job_id IS post_id -- no separate mapping table needed, Post.id is already a
unique key the callback can look up directly.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Post


class ImageServiceError(Exception):
    """Raised for invalid state transitions."""


class ImageBusyError(ImageServiceError):
    """Raised when another post is already image_queued -- maps to HTTP 409."""


def _data_images_dir() -> Path:
    d = Path(settings.data_dir) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def start_image_generation(db: Session, post_id: str) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise ImageServiceError(f"post {post_id} not found")
    # image_failed is a valid start state too -- it's the retry path (see
    # ImageStatus.tsx's Retry button). scene_instruction/seed/character_id
    # are already on the post from the original lock, nothing to re-derive.
    if post.status not in ("locked", "image_failed"):
        raise ImageServiceError(
            f"post {post_id} is not locked or retryable (status={post.status})")

    # Single-GPU pipeline, single-user tool -- no queue, just refuse a second
    # concurrent job rather than silently racing two ComfyUI renders.
    in_flight = (db.query(Post)
                .filter(Post.status == "image_queued")
                .filter(Post.id != post_id)
                .first())
    if in_flight is not None:
        raise ImageBusyError(
            f"post {in_flight.id} is already generating an image -- wait for it "
            "to finish (single-GPU pipeline, one job at a time)")

    callback_url = f"{settings.image_callback_base_url}/api/internal/image-callback"
    cmd = [
        settings.comfyui_env_python, "-m", "forge2.cli", "generate",
        post.character_id, post.scene_instruction,
        "--seed", str(post.seed),
        "--callback-url", callback_url,
        "--job-id", post.id,
    ]
    subprocess.Popen(cmd, cwd=settings.character_forge_v2_path,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    post.status = "image_queued"
    post.image_started_at = datetime.utcnow()
    post.image_job_error = None
    db.commit()
    db.refresh(post)
    return post


def handle_image_callback(db: Session, job_id: str, ok: bool,
                          image_path: str | None = None,
                          error: str | None = None) -> Post:
    """Called only by the forge2 subprocess, never by the frontend."""
    post = db.get(Post, job_id)
    if post is None:
        raise ImageServiceError(f"callback for unknown post/job_id {job_id}")

    if ok:
        dest = _data_images_dir() / f"{post.id}.png"
        shutil.copy(image_path, dest)
        post.final_image_path = str(dest)
        post.status = "image_ready"
        post.image_job_error = None
    else:
        post.status = "image_failed"
        post.image_job_error = error or "unknown error"

    db.commit()
    db.refresh(post)
    return post


def is_stalled(post: Post) -> bool:
    """True once a queued job has run past the configured stall timeout with
    no callback yet. Surfaced via GET /posts/{id} so the frontend can stop
    polling silently forever and tell the user to go check ComfyUI -- there's
    no watchdog daemon, this is a read-time check only."""
    if post.status != "image_queued" or post.image_started_at is None:
        return False
    elapsed = datetime.utcnow() - post.image_started_at
    return elapsed > timedelta(minutes=settings.image_stall_timeout_minutes)


def ensure_placeholder_image(character_id: str) -> Path | None:
    """Copy hero.png into our own data/images/ on first use so it's servable
    under the same /data static mount as real renders. Direct filesystem read
    of character-forge-v2's workspace -- no API call to System 1, both are
    local processes on the same machine. Returns None if that character's
    hero.png doesn't exist yet (no hero locked)."""
    dest = _data_images_dir() / f"placeholder_{character_id}.png"
    if dest.exists():
        return dest
    hero = Path(settings.character_forge_v2_path) / "workspace" / character_id / "hero.png"
    if not hero.exists():
        return None
    shutil.copy(hero, dest)
    return dest
