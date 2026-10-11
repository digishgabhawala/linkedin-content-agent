"""HTTP layer: compute actions acknowledge at once; status checks advance."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.db.database import Base, get_db
from app.main import app
from tests.test_steps import LONG_BRIEF, FakeQueue


class DownQueue(FakeQueue):
    async def post(self, url, json, timeout):
        raise httpx.ConnectError("down")


@pytest.fixture()
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    tc = TestClient(app)  # no `with`: lifespan (real init_db) is not run
    tc.queue = FakeQueue()  # tests may swap it (e.g. for a DownQueue)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    async def client():
        yield tc.queue

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[routes.get_http_client] = client
    app.dependency_overrides[routes.get_llm_client] = client
    yield tc
    app.dependency_overrides.clear()


def test_create_acknowledges_immediately_with_the_active_step(api):
    resp = api.post("/api/posts", json={"brief": LONG_BRIEF})
    assert resp.status_code == 200
    post = resp.json()
    assert post["status"] == "clarifying"
    assert post["active_step"]["name"] == "category"
    assert len(api.queue.submitted()) == 1


def test_status_check_advances_to_the_next_step(api):
    post_id = api.post("/api/posts", json={"brief": LONG_BRIEF}).json()["id"]
    api.queue.latest()["status"] = "claimed"
    view = api.get(f"/api/posts/{post_id}").json()
    assert view["active_step"]["task"]["status"] == "claimed"
    api.queue.finish('{"category": "lessons_learned"}')
    view = api.get(f"/api/posts/{post_id}").json()
    assert view["category"] == "lessons_learned" and view["active_step"]["name"] == "clarify"


def test_compute_action_on_busy_post_is_409(api):
    post_id = api.post("/api/posts", json={"brief": LONG_BRIEF}).json()["id"]
    resp = api.post(f"/api/posts/{post_id}/retry-step")
    assert resp.status_code == 409 and "busy" in resp.json()["detail"]


def test_failed_step_offers_retry(api):
    post_id = api.post("/api/posts", json={"brief": LONG_BRIEF}).json()["id"]
    api.queue.finish(error="expired: deadline passed before a worker was free")
    view = api.get(f"/api/posts/{post_id}").json()
    assert view["active_step"] is None and view["can_retry_step"] is True
    assert view["step_error"].startswith("expired:")
    view = api.post(f"/api/posts/{post_id}/retry-step").json()
    assert view["active_step"]["name"] == "category" and view["step_error"] is None


def test_unreachable_queue_is_503_and_nothing_is_half_applied(api):
    api.queue = DownQueue()
    resp = api.post("/api/posts", json={"brief": LONG_BRIEF})
    assert resp.status_code == 503 and "unreachable" in resp.json()["detail"]
    assert api.get("/api/posts").json() == []
