"""Another user's records are invisible: 404 (never 403) or an empty list."""
from tests.test_steps import LONG_BRIEF

API = "/api/linkedin"


def _post_as(api, users, user_id):
    users(user_id)
    return api.post(f"{API}/posts", json={"brief": LONG_BRIEF}).json()["id"]


def test_posts_are_private_to_their_owner(api, users):
    post_id = _post_as(api, users, "user-a")
    users("user-b")
    assert api.get(f"{API}/posts").json() == []
    for method, path, body in [
        ("get", "", None), ("get", "/drafts", None), ("get", "/feedback", None),
        ("post", "/feedback", {"stage": "draft", "user_note": "x"}),
        ("post", "/clarify", {"answer": "x"}), ("post", "/retry-step", None),
        ("post", "/accept-draft", None), ("post", "/finalize", None),
        ("patch", "/scene", {"scene_instruction": "x"}),
    ]:
        resp = api.request(method, f"{API}/posts/{post_id}{path}", json=body)
        assert resp.status_code == 404, f"{method} {path}: {resp.status_code}"
        assert "not found" in resp.json()["detail"]
    users("user-a")
    assert [p["id"] for p in api.get(f"{API}/posts").json()] == [post_id]


def test_new_posts_belong_to_their_creator(api, users):
    post_id = _post_as(api, users, "user-a")
    from app.db.models import Post
    with api.session_factory() as s:
        assert s.get(Post, post_id).owner_id == "user-a"
