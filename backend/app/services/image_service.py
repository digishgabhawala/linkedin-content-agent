"""image_service.py -- image-step helpers for the UI.

Image generation is the step engine's `image` step (services/steps.py): one
task-queue task, advanced lazily on status checks like every other step.
This module only interprets that step's live queue view (stalls, lost
workers, failure kinds) and serves the local hero placeholder.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings
from ..db.models import Post


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
