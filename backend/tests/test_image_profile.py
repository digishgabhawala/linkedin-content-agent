from datetime import datetime, timedelta, timezone

from app.auth import LOCAL_USER_ID
from app.db.models import Post
from app.services.image_service import (
    image_failure_kind,
    is_queue_delayed,
    is_stalled,
    is_worker_lost,
)


def test_queue_wait_does_not_count_as_render_stall():
    post = Post(
        owner_id=LOCAL_USER_ID,
        status="image_queued",
        image_started_at=datetime.utcnow() - timedelta(hours=2),
    )
    post.image_queue_status = "queued"
    post.image_claimed_at = None

    assert is_queue_delayed(post) is True
    assert is_stalled(post) is False


def test_render_stall_is_measured_from_claim_time():
    post = Post(
        owner_id=LOCAL_USER_ID,
        status="image_queued",
        image_started_at=datetime.utcnow() - timedelta(hours=2),
    )
    post.image_queue_status = "claimed"
    post.image_claimed_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    ).isoformat()

    assert is_queue_delayed(post) is False
    assert is_stalled(post) is False

    post.image_claimed_at = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    assert is_stalled(post) is True


def _claimed(lease):
    post = Post(owner_id=LOCAL_USER_ID, status="image_queued")
    post.image_queue_status = "claimed"
    post.image_lease_expires_at = lease
    return post


def test_worker_lost_when_rolling_lease_has_expired():
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert is_worker_lost(_claimed(past)) is True


def test_worker_lost_false_while_lease_in_future():
    future = (datetime.now(timezone.utc) + timedelta(minutes=200)).isoformat()
    assert is_worker_lost(_claimed(future)) is False


def test_worker_lost_false_without_lease():
    assert is_worker_lost(_claimed(None)) is False


def test_worker_lost_handles_z_suffix():
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert is_worker_lost(_claimed(past)) is True


def test_worker_lost_only_applies_to_claimed_tasks():
    post = _claimed((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    post.image_queue_status = "queued"
    assert is_worker_lost(post) is False


def test_failure_kind_corrupt_output():
    post = Post(owner_id=LOCAL_USER_ID, status="image_failed",
                image_job_error="corrupt_output: ComfyUI returned a blank/uniform image")
    assert image_failure_kind(post) == "corrupt_output"


def test_failure_kind_none_for_other_errors():
    assert image_failure_kind(Post(owner_id=LOCAL_USER_ID, status="image_failed",
                                   image_job_error="Command returned exit status 1")) is None
    assert image_failure_kind(Post(owner_id=LOCAL_USER_ID, status="image_failed", image_job_error=None)) is None
    assert image_failure_kind(Post(owner_id=LOCAL_USER_ID, status="image_ready",
                                   image_job_error="corrupt_output: stale")) is None


def test_failure_kind_insufficient_memory():
    post = Post(owner_id=LOCAL_USER_ID, status="image_failed",
                image_job_error="insufficient_memory: full quality needs 14 GB free")
    assert image_failure_kind(post) == "insufficient_memory"


def test_worker_lost_handles_naive_timestamp():
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()  # no timezone suffix
    assert is_worker_lost(_claimed(past)) is True
    future = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    assert is_worker_lost(_claimed(future)) is False
