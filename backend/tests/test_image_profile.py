import asyncio
from datetime import datetime, timedelta, timezone

from app.db.models import Post
from app.services.image_service import (
    is_queue_delayed,
    is_stalled,
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
