"""llm_client.py -- the app's only way to generate text.

Every LLM call becomes a `text_generation` task on the task-queue, run by
whichever local worker advertises that capability (today: Ollama on the
user's laptop; later possibly other providers -- chosen worker-side, never
here). This app never talks to an LLM directly.

Non-blocking (phase 3a): submit_* enqueue ONE step and return its task id
at once; get_task reads its status later. The step engine (steps.py) decides
what to submit next. Each task carries `deadline_at` (STEP_MAX_WAIT_MINUTES)
so a worker discards a step nobody can still use instead of running it late.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings

TEXT_TASK_TYPE = "text_generation"


@dataclass(frozen=True)
class LLMRequest:
    """One provider-neutral LLM call, built by an agent without any I/O."""
    messages: list[dict]
    temperature: float
    reasoning: bool
    response_format: str = "text"


# --- Non-blocking step API (phase 3a): submit one step, read its status later.

class TaskQueueUnavailable(Exception):
    """The task-queue could not be reached to submit a step."""


IMAGE_TASK_TYPE = "image_generation"


async def _post_task(client: httpx.AsyncClient, body: dict) -> str:
    try:
        resp = await client.post(f"{settings.task_queue_api_url}/tasks", json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]
    except httpx.HTTPError as e:
        raise TaskQueueUnavailable(
            f"Task queue unreachable at {settings.task_queue_url}: {e}") from e


async def submit_text(client: httpx.AsyncClient, req: LLMRequest) -> str:
    """Enqueue one LLM step and return its task id at once. No worker needs to
    be online: the task waits in the queue until one is (or until its
    deadline, after which the worker discards it as expired)."""
    deadline = datetime.now(timezone.utc) + timedelta(minutes=settings.step_max_wait_minutes)
    return await _post_task(client, {
        "task_type": TEXT_TASK_TYPE,
        "payload": {"messages": req.messages, "temperature": req.temperature,
                    "reasoning": req.reasoning, "response_format": req.response_format,
                    "deadline_at": deadline.isoformat()},
        "lease_minutes": 20,
        "retention_hours": 2,  # prompts carry post content through the hosted queue
    })


async def submit_image(client: httpx.AsyncClient, payload: dict) -> str:
    # 240-min lease: a full render on a loaded Mac has taken ~2h (see
    # image_service history); heartbeating workers shorten it anyway.
    return await _post_task(client, {"task_type": IMAGE_TASK_TYPE, "payload": payload,
                                  "lease_minutes": 240})


async def get_task(client: httpx.AsyncClient, task_id: str) -> dict:
    """The queue's current view of a step's task (status, result, error, progress)."""
    resp = await client.get(f"{settings.task_queue_api_url}/tasks/{task_id}", timeout=15)
    resp.raise_for_status()
    return resp.json()
