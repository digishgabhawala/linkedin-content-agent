import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.services.llm_client import (
    TextGenerationFailed,
    TextGenerationTimeout,
    TextGenerationUnavailable,
)


@pytest.mark.parametrize("exc, status", [
    (TextGenerationUnavailable("No worker can generate text right now"), 503),
    (TextGenerationFailed("text_unavailable: Ollama not reachable"), 502),
    (TextGenerationTimeout("No worker finished this text within 60 minutes"), 504),
])
def test_text_generation_errors_reach_the_ui_as_clear_http_errors(monkeypatch, exc, status):
    async def create_post(*args, **kwargs):
        raise exc

    monkeypatch.setattr(routes.ps, "create_post", create_post)
    # No `with`: skips lifespan, so the real posts.db is never opened.
    resp = TestClient(app).post("/api/posts", json={"brief": "x"})
    assert resp.status_code == status
    assert resp.json()["detail"] == str(exc)
