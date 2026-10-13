"""HTTP layer: compute actions acknowledge at once; status checks advance."""
import httpx

from app.db.database import get_db
from app.main import app
from tests.test_steps import LONG_BRIEF, FakeQueue


class DownQueue(FakeQueue):
    async def post(self, url, json, timeout):
        raise httpx.ConnectError("down")


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


def test_plain_actions_are_refused_while_a_step_runs(api):
    post_id = api.post("/api/posts", json={"brief": LONG_BRIEF}).json()["id"]
    for method, path, body in [("post", "accept-draft", None), ("patch", "scene", {"scene_instruction": "x"}),
                               ("post", "finalize", None)]:
        resp = getattr(api, method)(f"/api/posts/{post_id}/{path}", json=body)
        assert resp.status_code == 409, path


def test_every_compute_action_acknowledges_with_its_first_step(api):
    from app.db.models import Post
    session = next(app.dependency_overrides[get_db]())
    drafting = Post(character_id="gtee_dev", brief=LONG_BRIEF, status="drafting", post_text="p",
                    clarify_transcript="[]", category="lessons_learned")
    session.add(drafting)
    session.commit()
    pid = drafting.id
    assert api.post(f"/api/posts/{pid}/draft").json()["active_step"]["name"] == "draft"
    api.queue.finish(error="expired: x")
    api.get(f"/api/posts/{pid}")
    assert api.post(f"/api/posts/{pid}/regenerate",
                    json={"instruction": "tighter"}).json()["active_step"]["name"] == "rewrite"


def test_accept_draft_clears_a_stale_retry(api):
    from app.db.models import Post
    session = next(app.dependency_overrides[get_db]())
    post = Post(character_id="gtee_dev", brief="b", status="needs_input", post_text="p",
                clarify_transcript="[]", step_error="expired: x",
                step_context='{"automatic": true, "_retry": "judge"}')
    session.add(post)
    session.commit()
    view = api.post(f"/api/posts/{post.id}/accept-draft").json()
    assert view["status"] == "drafting" and view["step_error"] is None
    assert view["can_retry_step"] is False
