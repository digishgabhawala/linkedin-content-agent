"""image_service.py -- submits image generation as a task to the task-queue
service (see the sibling task-queue repo) instead of spawning
character-forge-v2 directly. Never imports forge2 or task-queue's own code
-- HTTP only, per this workspace's "standalone, shares nothing" convention.

This replaces the original subprocess.Popen + webhook-callback design.
That design assumed image generation always happened on THIS machine; the
task queue removes that assumption -- a worker running anywhere (this
machine, a friend's laptop, a Colab GPU session) can claim and complete the
task, and this service just polls for the result. Polling happens lazily,
on read (see sync_image_task, called from GET /posts/{id}), not via a
background thread -- same "nobody needs it noticed until someone actually
looks" reasoning as the task-queue's own lease-reclaim logic.
"""
from __future__ import annotations

import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Post
from .post_service import expand_scene_refs


class ImageServiceError(Exception):
    """Raised for invalid state transitions."""


async def start_image_generation(db: Session, client: httpx.AsyncClient, post_id: str,
                                 profile: str = "full") -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise ImageServiceError(f"post {post_id} not found")
    # image_failed (retry after a failure) and image_ready (re-roll a
    # technically-successful-but-unwanted render, e.g. garbled in-image text)
    # are both valid start states too, alongside the normal first-time
    # "locked" path. scene_instruction/character_id are already on the post
    # from the original lock, nothing to re-derive.
    if post.status not in ("locked", "image_failed", "image_ready"):
        raise ImageServiceError(
            f"post {post_id} is not locked or retryable (status={post.status})")

    # A retry or re-roll MUST get a fresh seed -- ComfyUI/forge2 caches
    # per-node outputs keyed on exact input values including seed;
    # resubmitting the identical seed replays whatever was cached last time
    # (including a corrupted result) with no real compute at all. Confirmed
    # live during the original Popen-based design; still true here since
    # the worker on the other end is the same forge2.
    if post.status in ("image_failed", "image_ready"):
        post.seed = random.randint(1, 999_999)

    # scene_instruction may hold short "@name" references (e.g. "@office")
    # rather than full backdrop text -- expand those to their current
    # detail_text here, at the last possible moment, never persisted. This
    # is what makes editing a SceneAsset's detail_text retroactively apply
    # to any post that still references it, instead of baking in a stale
    # copy at lock time (see post_service.expand_scene_refs).
    task_text = expand_scene_refs(db, post.scene_instruction)

    resp = await client.post(f"{settings.task_queue_url}/api/tasks", json={
        "task_type": "image_generation",
        "payload": {"character_id": post.character_id, "task": task_text,
                    "seed": post.seed, "profile": profile},
        # Explicit, generous lease -- the task-queue's generic default (60 min)
        # is sized for short tasks, not this one. Found live: a real render on
        # a loaded Mac took ~2 hours; a 60-min lease expired mid-render and let
        # a second worker legitimately reclaim and "complete" the task with a
        # different result while the original worker was still genuinely
        # working. 240 min matches forge2's own comfy.timeout_s (2h) plus
        # real headroom, not just the observed worst case.
        "lease_minutes": 240,
    }, timeout=30)
    resp.raise_for_status()
    task = resp.json()

    post.image_task_id = task["id"]
    post.status = "image_queued"
    post.image_started_at = datetime.utcnow()
    post.image_job_error = None
    db.commit()
    db.refresh(post)
    post.image_queue_status = task.get("status", "queued")
    post.image_claimed_at = task.get("claimed_at")
    return post


async def sync_image_task(db: Session, client: httpx.AsyncClient, post: Post) -> Post:
    """Checks the task-queue for this post's in-flight image task and
    updates the post if it's since finished. No-op if the post isn't
    actually waiting on one. Called from GET /posts/{id} so the frontend's
    existing 3s poll is what drives this -- no separate background poller
    needed."""
    if post.status != "image_queued" or not post.image_task_id:
        return post

    try:
        resp = await client.get(f"{settings.task_queue_url}/api/tasks/{post.image_task_id}", timeout=15)
        resp.raise_for_status()
        task = resp.json()
        post.image_queue_status = task.get("status")
        post.image_claimed_at = task.get("claimed_at")
        post.image_worker_id = task.get("claimed_by")
        post.image_lease_expires_at = task.get("lease_expires_at")
        post.image_progress_stage = task.get("progress_stage")
        post.image_progress_message = task.get("progress_message")
        post.image_progress_updated_at = task.get("progress_updated_at")

        if task["status"] == "done":
            artifact_id = task["result"]["image_artifact_id"]
            artifact_resp = await client.get(
                f"{settings.task_queue_url}/api/artifacts/{artifact_id}", timeout=15)
            artifact_resp.raise_for_status()
            post.final_image_path = artifact_resp.json()["url"]
    except httpx.HTTPError:
        # Transient network blip / task-queue redeploy shouldn't break
        # viewing this post's status -- the next 3s poll just tries again.
        # is_stalled() (a separate, time-based check) is what actually
        # surfaces a genuinely stuck render to the user.
        return post

    if task["status"] == "done":
        post.status = "image_ready"
        post.image_job_error = None
        db.commit()
        db.refresh(post)
    elif task["status"] == "failed":
        post.status = "image_failed"
        post.image_job_error = task.get("error") or "unknown error"
        db.commit()
        db.refresh(post)
    # queued/claimed: still in flight, nothing to update yet.

    return post


def _elapsed_since(value: datetime | str | None) -> timedelta | None:
    """Return elapsed UTC time for either a DB datetime or queue ISO timestamp."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is not None:
        return datetime.now(timezone.utc) - value.astimezone(timezone.utc)
    return datetime.utcnow() - value


def is_queue_delayed(post: Post) -> bool:
    """True when a task has waited unusually long without being claimed."""
    if (post.status != "image_queued"
            or getattr(post, "image_queue_status", None) != "queued"):
        return False
    elapsed = _elapsed_since(post.image_started_at)
    return elapsed is not None and elapsed > timedelta(
        minutes=settings.image_stall_timeout_minutes)


def is_stalled(post: Post) -> bool:
    """True when an actively claimed render exceeds the runtime threshold.

    Queue wait time is deliberately excluded: rendering begins at the hosted
    queue's claimed_at timestamp, not when this app originally submitted the
    task. The task queue's lease/reclaim mechanism remains independent.
    """
    if (post.status != "image_queued"
            or getattr(post, "image_queue_status", None) != "claimed"):
        return False
    elapsed = _elapsed_since(getattr(post, "image_claimed_at", None))
    if elapsed is None:
        return False
    return elapsed > timedelta(minutes=settings.image_stall_timeout_minutes)


def is_worker_lost(post: Post) -> bool:
    """True when the worker holding this task stopped heartbeating.

    Heartbeating workers renew a short rolling lease (task-queue's
    ACTIVE_LEASE_MINUTES) every minute, so a claimed task whose lease is
    already in the past has no live worker. The queue reclaims it lazily on
    the next claim attempt -- until then it still reads as "claimed". Older
    workers that never heartbeat keep the producer's 240-min lease and so
    are only reported lost after that, never early.
    """
    if (post.status != "image_queued"
            or getattr(post, "image_queue_status", None) != "claimed"):
        return False
    # _elapsed_since returns now - lease: positive means the lease has passed.
    past_lease = _elapsed_since(getattr(post, "image_lease_expires_at", None))
    return past_lease is not None and past_lease > timedelta(0)


CORRUPT_OUTPUT_PREFIX = "corrupt_output:"
INSUFFICIENT_MEMORY_PREFIX = "insufficient_memory:"


def image_failure_kind(post: Post) -> str | None:
    """Classify a failed render so the UI can explain it.

    The task-queue image worker prefixes blank/uniform renders (forge2 exit
    code 3) with "corrupt_output:". Retry stays manual and already uses a
    fresh seed -- this only changes the message the user sees.
    """
    if post.status != "image_failed" or not post.image_job_error:
        return None
    if post.image_job_error.startswith(CORRUPT_OUTPUT_PREFIX):
        return "corrupt_output"
    # The worker refuses a Full render it has no memory for; the user then
    # chooses Lightning (or frees memory) -- never downgraded automatically.
    if post.image_job_error.startswith(INSUFFICIENT_MEMORY_PREFIX):
        return "insufficient_memory"
    return None


def ensure_placeholder_image(character_id: str) -> Path | None:
    """Copy hero.png into our own generated/images/ on first use so it's
    servable under the same /generated static mount as real renders. Direct
    filesystem read of character-forge-v2's workspace -- no API call needed
    when both are local processes on the same machine. Returns None if that
    character's hero.png doesn't exist (no hero locked, OR
    character-forge-v2 simply isn't present on this machine at all -- e.g.
    once image generation runs entirely on a separate worker machine, this
    just gracefully stops offering a placeholder rather than erroring)."""
    d = Path(settings.generated_dir) / "images"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"placeholder_{character_id}.png"
    if dest.exists():
        return dest
    hero = Path(settings.character_forge_v2_path) / "workspace" / character_id / "hero.png"
    if not hero.exists():
        return None
    shutil.copy(hero, dest)
    return dest
