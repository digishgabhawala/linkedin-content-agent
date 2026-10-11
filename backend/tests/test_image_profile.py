import asyncio
from datetime import datetime, timedelta, timezone

from app.db.models import Post
from app.services.image_service import (
    image_failure_kind,
    is_queue_delayed,
    is_stalled,
    is_worker_lost,
    start_image_generation,
    sync_image_task,
)


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {"id": "task-123", "status": "queued"}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.body = None

    async def post(self, url, json, timeout):
        self.body = json
        return FakeResponse()

    async def get(self, url, timeout):
        return FakeResponse({
            "id": "task-123",
            "status": "claimed",
            "claimed_at": "2026-10-11T01:15:00+00:00",
        })


def test_selected_profile_is_written_to_task_payload(db_session):
    post = Post(
        character_id="gtee_dev",
        brief="brief",
        status="locked",
        scene_instruction="turning a dial",
        seed=42,
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    client = FakeClient()

    result = asyncio.run(start_image_generation(
        db_session, client, post.id, profile="lightning"))

    assert client.body["payload"]["profile"] == "lightning"
    assert client.body["lease_minutes"] == 240
    assert result.image_queue_status == "queued"


def test_claimed_queue_task_is_exposed_as_active_rendering(db_session):
    post = Post(
        character_id="gtee_dev",
        brief="brief",
        status="image_queued",
        scene_instruction="turning a dial",
        seed=42,
        image_task_id="task-123",
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    result = asyncio.run(sync_image_task(db_session, FakeClient(), post))

    assert result.image_queue_status == "claimed"
    assert result.image_claimed_at == "2026-10-11T01:15:00+00:00"


def test_queue_wait_does_not_count_as_render_stall():
    post = Post(
        status="image_queued",
        image_started_at=datetime.utcnow() - timedelta(hours=2),
    )
    post.image_queue_status = "queued"
    post.image_claimed_at = None

    assert is_queue_delayed(post) is True
    assert is_stalled(post) is False


def test_render_stall_is_measured_from_claim_time():
    post = Post(
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


class ProgressClient(FakeClient):
    async def get(self, url, timeout):
        return FakeResponse({
            "id": "task-123",
            "status": "claimed",
            "claimed_at": "2026-10-11T01:15:00+00:00",
            "claimed_by": "image-worker-mac",
            "lease_expires_at": "2099-01-01T00:00:00+00:00",
            "progress_stage": "rendering",
            "progress_message": "Character Forge and ComfyUI are generating the image",
            "progress_updated_at": "2026-10-11T01:16:00+00:00",
        })


def _queued_post(db_session):
    post = Post(character_id="gtee_dev", brief="brief", status="image_queued",
                scene_instruction="turning a dial", seed=42, image_task_id="task-123")
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


def test_sync_exposes_task_progress_and_worker(db_session):
    result = asyncio.run(sync_image_task(db_session, ProgressClient(), _queued_post(db_session)))

    assert result.image_progress_stage == "rendering"
    assert result.image_progress_message.startswith("Character Forge")
    assert result.image_progress_updated_at == "2026-10-11T01:16:00+00:00"
    assert result.image_worker_id == "image-worker-mac"
    assert is_worker_lost(result) is False


def _claimed(lease):
    post = Post(status="image_queued")
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
    post = Post(status="image_failed",
                image_job_error="corrupt_output: ComfyUI returned a blank/uniform image")
    assert image_failure_kind(post) == "corrupt_output"


def test_failure_kind_none_for_other_errors():
    assert image_failure_kind(Post(status="image_failed",
                                   image_job_error="Command returned exit status 1")) is None
    assert image_failure_kind(Post(status="image_failed", image_job_error=None)) is None
    assert image_failure_kind(Post(status="image_ready",
                                   image_job_error="corrupt_output: stale")) is None
