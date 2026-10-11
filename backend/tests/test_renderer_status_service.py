import asyncio

import httpx

from app.services.renderer_status_service import (
    hosted_renderer_status,
    summarize_workers,
)


def _worker(id, online=True, state="idle", task_types=("image_generation",), **extra):
    return {"id": id, "name": id, "capabilities": {"task_types": list(task_types)},
            "state": state, "current_task_id": None, "online": online,
            "last_heartbeat_at": "2026-10-11T10:00:00+00:00", "details": {}} | extra


def test_summary_counts_only_online_image_workers():
    result = summarize_workers([
        _worker("mac"),
        _worker("old-colab", online=False),
        _worker("text-only", task_types=("text_generation",)),
    ])
    assert result["online"] is True
    assert result["online_count"] == 1
    assert [w["id"] for w in result["workers"]] == ["mac"]
    assert result["message"] == "1 image worker online"


def test_all_busy_message():
    result = summarize_workers([_worker("mac", state="busy")])
    assert result["busy_count"] == 1
    assert result["message"] == "1 image worker online, busy"


def test_no_online_worker_reports_last_seen():
    result = summarize_workers([
        _worker("a", online=False, last_heartbeat_at="2026-10-10T09:00:00+00:00"),
        _worker("b", online=False, last_heartbeat_at="2026-10-11T08:00:00+00:00"),
    ])
    assert result["online"] is False
    assert result["last_seen_at"] == "2026-10-11T08:00:00+00:00"
    assert result["message"] == "No image worker online"


def test_never_registered_message():
    assert summarize_workers([])["message"] == "No image worker has registered yet"


def test_worker_without_details_defaults_to_empty():
    w = _worker("mac")
    del w["details"]
    assert summarize_workers([w])["workers"][0]["details"] == {}


class FailingClient:
    async def get(self, url, timeout):
        raise httpx.ConnectError("down")


def test_unreachable_queue_reports_unreachable():
    result = asyncio.run(hosted_renderer_status(FailingClient()))
    assert result["reachable"] is False
    assert result["online"] is False
    assert result["message"] == "Task queue unreachable"
