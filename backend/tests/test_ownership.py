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


def test_backdrops_are_private_and_names_are_per_owner(api, users):
    users("user-a")
    assert api.post(f"{API}/scene-assets", json={"display_name": "Office", "detail_text": "A"}
                    ).status_code == 201
    users("user-b")
    assert api.get(f"{API}/scene-assets?include_archived=true").json() == []
    assert api.get(f"{API}/scene-assets/office/versions").json() == []
    for method, path, body in [("patch", "", {"detail_text": "x"}), ("post", "/archive", None),
                               ("post", "/unarchive", None), ("delete", "", None),
                               ("post", "/versions/1/restore", None)]:
        assert api.request(method, f"{API}/scene-assets/office{path}", json=body).status_code == 404
    assert api.post(f"{API}/scene-assets", json={"display_name": "Office", "detail_text": "B"}
                    ).status_code == 201


def test_characters_and_hero_runs_are_private(api, users, monkeypatch):
    from tests.test_character_studio_routes import CARD, _studio_queue
    users("user-a")
    _studio_queue(api, monkeypatch)
    assert api.post(f"{API}/characters", json=CARD).status_code == 201
    run = api.post(f"{API}/characters/new_dev/hero-generations",
                   json={"candidate_count": 1, "base_seed": 1}).json()
    users("user-b")
    assert api.get(f"{API}/characters").json() == []
    for method, path, body in [
        ("get", "", None), ("get", "/hero-generations", None),
        ("post", "/hero-generations", {"candidate_count": 1}),
        ("get", f"/hero-generations/{run['id']}", None),
        ("post", f"/hero-candidates/{run['candidates'][0]['id']}/lock", None),
    ]:
        assert api.request(method, f"{API}/characters/new_dev{path}", json=body
                           ).status_code == 404, path
    # ids stay globally unique (stable global IDs, spec Q7): a clash is a 409
    assert api.post(f"{API}/characters", json=CARD).status_code == 409
