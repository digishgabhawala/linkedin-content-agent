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


def readiness_from_workers(workers: list[dict]) -> dict:
    """Full-quality memory readiness, as measured BY the image worker.

    The worker may be another machine, so this app's own free memory is
    irrelevant. With several workers, report the roomiest. Without any
    worker-reported memory (e.g. a queue that predates heartbeat details),
    answer "unknown" and don't block: the worker enforces the limit anyway
    and fails the task with `insufficient_memory:` if Full can't run.
    """
    measured = [w for w in workers
                if _supports_images(w) and w.get("online")
                and ((w.get("details") or {}).get("memory") or {}).get("available_gb") is not None]
    if not measured:
        return {"source": "unknown", "worker_name": None, "available_gb": None,
                "recommended_gb": None, "enough_memory": True, "top_consumers": []}
    best = max(measured, key=lambda w: w["details"]["memory"]["available_gb"])
    mem = best["details"]["memory"]
    required = (mem.get("required_gb") or {}).get("full", 0.0)
    comfyui = best["details"].get("comfyui") or {}
    ollama = best["details"].get("ollama") or {}
    # Memory the worker frees by itself before rendering doesn't count as
    # "used": its own idle ComfyUI (stopped before refusing a render) and its
    # own loaded Ollama model (always unloaded before an image task). Things
    # the user started are never touched, so those still count.
    reclaimable = best.get("state") != "busy" and (
        comfyui.get("managed") is True
        or (ollama.get("managed") is True and ollama.get("loaded") is True))
    return {
        "source": "worker",
        "worker_name": best.get("name") or best.get("id"),
        "available_gb": mem["available_gb"],
        "recommended_gb": required,
        "enough_memory": reclaimable or mem["available_gb"] >= required,
        "top_consumers": mem.get("top_consumers") or [],
    }


async def _fetch_workers(client: httpx.AsyncClient) -> list[dict] | None:
    try:
        resp = await client.get(f"{settings.task_queue_url}/api/workers", timeout=10)
        resp.raise_for_status()
        workers = resp.json()
    except (httpx.HTTPError, ValueError):  # ValueError: body isn't JSON
        return None
    # Anything but a list (an error object, a proxy page parsed as JSON) is
    # not a worker registry -- treat it like an unreachable queue.
    return workers if isinstance(workers, list) else None


async def hosted_renderer_status(client: httpx.AsyncClient) -> dict:
    workers = await _fetch_workers(client)
    if workers is None:
        return {"reachable": False, "online": False, "online_count": 0, "busy_count": 0,
                "last_seen_at": None, "message": "Task queue unreachable", "workers": []}
    return summarize_workers(workers)


async def hosted_image_readiness(client: httpx.AsyncClient) -> dict:
    return readiness_from_workers(await _fetch_workers(client) or [])
