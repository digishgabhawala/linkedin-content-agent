"""llm_client.py -- the app's only way to generate text.

Every LLM call becomes a `text_generation` task on the task-queue, run by
whichever local worker advertises that capability (today: Ollama on the
user's laptop; later possibly other providers -- chosen worker-side, never
here). This app never talks to an LLM directly.

Phase-1 shape: the caller awaits the result (submit, then poll). A worker
busy rendering an image finishes that first, so a call may wait; it gives up
after TEXT_MAX_WAIT_MINUTES, and the task carries the same `deadline_at` so
the worker discards it instead of running it late.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings

TEXT_TASK_TYPE = "text_generation"
# Poll quickly at first (most calls finish in well under a minute), then
# back off so a call waiting behind a long render doesn't hammer the hosted
# queue. Re-check periodically that a text-capable worker still exists, so a
# laptop that sleeps mid-pipeline fails the request instead of hanging it.
FAST_POLL_PHASE_SECONDS = 20
SLOW_POLL_SECONDS = 3
WORKER_RECHECK_SECONDS = 30


class TextGenerationUnavailable(Exception):
    """No online worker can generate text."""


class TextGenerationFailed(Exception):
    """The worker reported a failure (message carries its error)."""


class TextGenerationTimeout(Exception):
    """Gave up waiting for a worker within TEXT_MAX_WAIT_MINUTES."""


async def _text_worker_online(client: httpx.AsyncClient) -> bool:
    resp = await client.get(f"{settings.task_queue_url}/api/workers", timeout=15)
    resp.raise_for_status()
    workers = resp.json()
    return isinstance(workers, list) and any(
        w.get("online") and TEXT_TASK_TYPE in ((w.get("capabilities") or {}).get("task_types") or [])
        for w in workers)


async def chat(client: httpx.AsyncClient, messages: list[dict], *, temperature: float,
               reasoning: bool, response_format: str = "text") -> str:
    try:
        task_id, deadline = await _submit(client, messages, temperature, reasoning,
                                          response_format)
    except httpx.HTTPError as e:
        raise TextGenerationUnavailable(
            f"Task queue unreachable at {settings.task_queue_url}: {e}") from e
    return await _await_result(client, task_id, deadline)


async def _submit(client: httpx.AsyncClient, messages: list[dict], temperature: float,
                  reasoning: bool, response_format: str) -> tuple[str, datetime]:
    if not await _text_worker_online(client):
        raise TextGenerationUnavailable(
            "No worker can generate text right now -- start the local worker on your laptop.")

    deadline = datetime.now(timezone.utc) + timedelta(minutes=settings.text_max_wait_minutes)
    resp = await client.post(f"{settings.task_queue_url}/api/tasks", json={
        "task_type": TEXT_TASK_TYPE,
        "payload": {
            "messages": messages,
            "temperature": temperature,
            "reasoning": reasoning,
            "response_format": response_format,
            "deadline_at": deadline.isoformat(),
        },
        # Generation itself takes minutes at most; the wait behind a render
        # happens while the task is still queued, before any lease starts.
        "lease_minutes": 20,
        # Prompts carry post content through the hosted queue: keep briefly.
        "retention_hours": 2,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"], deadline


async def _await_result(client: httpx.AsyncClient, task_id: str, deadline: datetime) -> str:
    waited = since_check = 0.0
    while True:
        interval = (settings.text_poll_seconds if waited < FAST_POLL_PHASE_SECONDS
                    else max(settings.text_poll_seconds, SLOW_POLL_SECONDS))
        await asyncio.sleep(interval)
        waited += interval
        since_check += interval
        try:
            poll = await client.get(f"{settings.task_queue_url}/api/tasks/{task_id}", timeout=15)
            poll.raise_for_status()
            task = poll.json()
        except httpx.HTTPError:
            task = {"status": "unknown"}  # transient blip: keep waiting until the deadline
        if task["status"] == "done":
            return (task.get("result") or {}).get("content", "")
        if task["status"] == "failed":
            raise TextGenerationFailed(task.get("error") or "text generation failed")
        if datetime.now(timezone.utc) > deadline:
            raise TextGenerationTimeout(
                f"No worker finished this text within {settings.text_max_wait_minutes:g} "
                "minutes (it may be busy rendering an image). Try again later.")
        if since_check >= WORKER_RECHECK_SECONDS:
            since_check = 0.0
            try:
                still_there = await _text_worker_online(client)
            except httpx.HTTPError:
                still_there = True  # a registry blip is not evidence the worker is gone
            if not still_there:
                raise TextGenerationUnavailable(
                    "The worker went offline while this text was waiting -- restart the "
                    "local worker on your laptop and try again.")
