"""Own and release only the Ollama model loaded by this application."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx

from ..config import settings

log = logging.getLogger(__name__)
_ollama_session_lock = asyncio.Lock()


def _model_is_loaded(payload: dict, model: str) -> bool:
    return any(
        item.get("name") == model or item.get("model") == model
        for item in payload.get("models", [])
    )


@asynccontextmanager
async def owned_ollama_session(client: httpx.AsyncClient):
    """Serialize app Ollama work and unload only a model this session loaded.

    If Ollama cannot report its current models, cleanup is deliberately
    skipped: preserving a possibly user-owned model is safer than guessing.
    """
    async with _ollama_session_lock:
        loaded_before = True
        try:
            response = await client.get(f"{settings.ollama_url}/api/ps", timeout=10)
            response.raise_for_status()
            loaded_before = _model_is_loaded(response.json(), settings.ollama_model)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Could not inspect Ollama model ownership; cleanup disabled: %s", exc)

        try:
            yield
        finally:
            if not loaded_before:
                try:
                    response = await client.post(
                        f"{settings.ollama_url}/api/generate",
                        json={"model": settings.ollama_model, "keep_alive": 0},
                        timeout=30,
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    # Content creation already succeeded; memory cleanup should
                    # never turn a successful user operation into a failure.
                    log.warning("Could not unload app-owned Ollama model %s: %s",
                                settings.ollama_model, exc)
