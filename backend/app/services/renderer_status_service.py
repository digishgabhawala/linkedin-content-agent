"""Image-renderer availability, read from the hosted task-queue's worker
registry over HTTP (never imports task-queue code). Replaces the old local
`ps` + ComfyUI ping, which reported "offline" whenever the worker ran on a
different machine (e.g. Colab)."""
from __future__ import annotations

import httpx

from ..config import settings

IMAGE_TASK_TYPE = "image_generation"


def _supports_images(worker: dict) -> bool:
    capabilities = worker.get("capabilities") or {}
    return IMAGE_TASK_TYPE in (capabilities.get("task_types") or [])


def _worker_view(worker: dict) -> dict:
    return {
        "id": worker.get("id"),
        "name": worker.get("name") or worker.get("id"),
        "state": worker.get("state"),
        "current_task_id": worker.get("current_task_id"),
        "last_heartbeat_at": worker.get("last_heartbeat_at"),
        "details": worker.get("details") or {},
    }


def summarize_workers(workers: list[dict]) -> dict:
    image_workers = [w for w in workers if _supports_images(w)]
    online = [w for w in image_workers if w.get("online")]
    busy = [w for w in online if w.get("state") == "busy"]

    if not image_workers:
        message = "No image worker has registered yet"
    elif not online:
        message = "No image worker online"
    else:
        noun = "worker" if len(online) == 1 else "workers"
        message = f"{len(online)} image {noun} online"
        if len(busy) == len(online):
            message += ", busy"

    # task-queue emits one consistent ISO format, so max() on strings is safe.
    seen = [w["last_heartbeat_at"] for w in image_workers if w.get("last_heartbeat_at")]
    return {
        "reachable": True,
        "online": bool(online),
        "online_count": len(online),
        "busy_count": len(busy),
        # Only meaningful when nobody is online: "last seen 3h ago".
        "last_seen_at": None if online or not seen else max(seen),
        "message": message,
        "workers": [_worker_view(w) for w in online],
    }


async def hosted_renderer_status(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.get(f"{settings.task_queue_url}/api/workers", timeout=10)
        resp.raise_for_status()
        workers = resp.json()
    except httpx.HTTPError:
        return {"reachable": False, "online": False, "online_count": 0, "busy_count": 0,
                "last_seen_at": None, "message": "Task queue unreachable", "workers": []}
    return summarize_workers(workers)
