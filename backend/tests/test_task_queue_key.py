import asyncio

from app.api import routes
from app.config import Settings


async def _first(gen):
    client = await gen.__anext__()
    headers = dict(client.headers)
    await gen.aclose()
    return headers


def test_task_queue_calls_carry_the_app_key(monkeypatch):
    monkeypatch.setattr(routes.settings, "task_queue_api_key", "raw-key-123")
    for dep in (routes.get_http_client, routes.get_llm_client):
        assert asyncio.run(_first(dep()))["x-api-key"] == "raw-key-123"


def test_no_key_configured_sends_no_header(monkeypatch):
    monkeypatch.setattr(routes.settings, "task_queue_api_key", None)
    assert "x-api-key" not in asyncio.run(_first(routes.get_http_client()))


def test_key_is_configuration():
    assert Settings(_env_file=None, task_queue_api_key="k").task_queue_api_key == "k"
