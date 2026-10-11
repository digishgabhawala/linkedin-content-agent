import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.services import llm_client
from app.services.llm_client import (
    TextGenerationFailed,
    TextGenerationTimeout,
    TextGenerationUnavailable,
    chat,
)

TEXT_WORKER = {"id": "mac", "online": True, "capabilities": {"task_types": ["text_generation"]}}
IMAGE_ONLY = {"id": "gpu", "online": True, "capabilities": {"task_types": ["image_generation"]}}
OFFLINE_TEXT = TEXT_WORKER | {"id": "old", "online": False}


class Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeQueue:
    def __init__(self, workers, statuses, workers_later=None, down=False):
        self.workers, self.statuses = workers, list(statuses)
        self.workers_later = workers_later  # registry after the first check
        self.down = down
        self.submitted = None
        self.polls = 0
        self.worker_checks = 0

    async def get(self, url, timeout):
        if self.down:
            raise httpx.ConnectError("queue down")
        if url.endswith("/api/workers"):
            self.worker_checks += 1
            if self.worker_checks > 1 and self.workers_later is not None:
                return Resp(self.workers_later)
            return Resp(self.workers)
        self.polls += 1
        return Resp(self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0])

    async def post(self, url, json, timeout):
        self.submitted = json
        return Resp({"id": "task-1", "status": "queued"})


SLEPT = []


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    SLEPT.clear()

    async def no_sleep(seconds):
        SLEPT.append(seconds)

    monkeypatch.setattr(llm_client.asyncio, "sleep", no_sleep)


MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_returns_worker_content_and_submits_contract():
    q = FakeQueue([TEXT_WORKER], [{"status": "queued"}, {"status": "claimed"},
                                 {"status": "done", "result": {"content": "the draft"}}])
    out = asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=True, response_format="json"))
    assert out == "the draft"
    body = q.submitted
    assert body["task_type"] == "text_generation"
    assert body["lease_minutes"] == 20 and body["retention_hours"] == 2
    p = body["payload"]
    assert p["messages"] == MESSAGES and p["temperature"] == 0.2
    assert p["reasoning"] is True and p["response_format"] == "json"
    deadline = datetime.fromisoformat(p["deadline_at"].replace("Z", "+00:00"))
    assert deadline > datetime.now(timezone.utc)


def test_fails_fast_without_a_text_capable_online_worker():
    q = FakeQueue([IMAGE_ONLY, OFFLINE_TEXT], [{"status": "done"}])
    with pytest.raises(TextGenerationUnavailable):
        asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False))
    assert q.submitted is None


def test_failed_task_raises_with_worker_error():
    q = FakeQueue([TEXT_WORKER], [{"status": "failed", "error": "text_unavailable: Ollama down"}])
    with pytest.raises(TextGenerationFailed, match="Ollama down"):
        asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False))


def test_gives_up_at_the_deadline(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "text_max_wait_minutes", 0)
    q = FakeQueue([TEXT_WORKER], [{"status": "queued"}])
    with pytest.raises(TextGenerationTimeout):
        asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False))


def test_worker_vanishing_while_waiting_fails_fast_instead_of_hanging():
    q = FakeQueue([TEXT_WORKER], [{"status": "queued"}], workers_later=[OFFLINE_TEXT])
    with pytest.raises(TextGenerationUnavailable, match="went offline"):
        asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False))
    assert q.polls < 100  # gave up long before the 60-minute deadline


def test_unreachable_queue_is_reported_as_unavailable():
    q = FakeQueue([TEXT_WORKER], [{"status": "done"}], down=True)
    with pytest.raises(TextGenerationUnavailable, match="[Tt]ask queue"):
        asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False))


def test_polling_backs_off_during_a_long_wait():
    statuses = [{"status": "queued"}] * 60 + [{"status": "done", "result": {"content": "ok"}}]
    q = FakeQueue([TEXT_WORKER], statuses)
    assert asyncio.run(chat(q, MESSAGES, temperature=0.2, reasoning=False)) == "ok"
    assert SLEPT[0] == 1 and max(SLEPT) >= 3  # quick at first, slower later
