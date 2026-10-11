import asyncio

import httpx

from app.services.renderer_status_service import (
    hosted_image_readiness,
    hosted_renderer_status,
    readiness_from_workers,
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


def _mem(available, full=14.0, consumers=()):
    return {"memory": {"available_gb": available, "required_gb": {"full": full, "lightning": 0.0},
                       "top_consumers": list(consumers)}}


def test_readiness_uses_worker_reported_memory():
    result = readiness_from_workers([
        _worker("mac", details=_mem(9.5, consumers=[{"name": "Ollama", "memory_gb": 9.1}])),
    ])
    assert result["source"] == "worker"
    assert result["worker_name"] == "mac"
    assert result["available_gb"] == 9.5
    assert result["recommended_gb"] == 14.0
    assert result["enough_memory"] is False
    assert result["top_consumers"] == [{"name": "Ollama", "memory_gb": 9.1}]


def test_readiness_prefers_the_worker_with_most_free_memory():
    result = readiness_from_workers([
        _worker("busy-mac", details=_mem(6.0)),
        _worker("colab", details=_mem(40.0)),
        _worker("offline", online=False, details=_mem(99.0)),
    ])
    assert result["worker_name"] == "colab"
    assert result["enough_memory"] is True


def test_readiness_unknown_without_worker_memory_does_not_block():
    result = readiness_from_workers([_worker("mac")])  # details == {} (pre-rollout queue)
    assert result["source"] == "unknown"
    assert result["enough_memory"] is True


def test_readiness_unknown_when_queue_unreachable():
    result = asyncio.run(hosted_image_readiness(FailingClient()))
    assert result["source"] == "unknown"
    assert result["enough_memory"] is True
