import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.config import settings
from app.db.models import Post
from app.services.llm_client import (
    LLMRequest,
    TaskQueueUnavailable,
    get_task,
    submit_image,
    submit_text,
)


class Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class Queue:
    def __init__(self, down=False):
        self.down, self.posted = down, None

    async def post(self, url, json, timeout):
        if self.down:
            raise httpx.ConnectError("down")
        self.posted = (url, json)
        return Resp({"id": "task-9", "status": "queued"})

    async def get(self, url, timeout):
        if self.down:
            raise httpx.ConnectError("down")
        return Resp({"id": url.rsplit("/", 1)[1], "status": "claimed", "progress_stage": "generating_text"})


REQ = LLMRequest([{"role": "user", "content": "hi"}], temperature=0.3, reasoning=False,
                 response_format="json")


def test_submit_text_enqueues_and_returns_immediately_with_task_id():
    q = Queue()
    assert asyncio.run(submit_text(q, REQ)) == "task-9"
    url, body = q.posted
    assert url == f"{settings.task_queue_api_url}/tasks"
    assert body["task_type"] == "text_generation"
    assert body["payload"]["messages"] == REQ.messages
    assert body["payload"]["response_format"] == "json" and body["payload"]["reasoning"] is False
    assert body["lease_minutes"] == 20 and body["retention_hours"] == 2
    deadline = datetime.fromisoformat(body["payload"]["deadline_at"])
    assert deadline > datetime.now(timezone.utc)


def test_submit_does_not_require_an_online_worker():
    # Accept and queue: a worker may come online later (no /api/workers check).
    q = Queue()
    asyncio.run(submit_text(q, REQ))
    assert q.posted is not None


def test_submit_image_uses_long_lease():
    q = Queue()
    payload = {"character_id": "gtee_dev", "task": "waving", "seed": 1, "profile": "lightning"}
    assert asyncio.run(submit_image(q, payload)) == "task-9"
    assert q.posted[1]["task_type"] == "image_generation" and q.posted[1]["lease_minutes"] == 240


def test_unreachable_queue_raises_clear_error():
    with pytest.raises(TaskQueueUnavailable, match="unreachable"):
        asyncio.run(submit_text(Queue(down=True), REQ))


def test_get_task_returns_queue_view():
    assert asyncio.run(get_task(Queue(), "task-9"))["status"] == "claimed"


def test_post_has_step_columns():
    post = Post(active_step='{"name": "judge"}', step_context="{}", step_error=None)
    assert post.active_step and post.step_context == "{}"
