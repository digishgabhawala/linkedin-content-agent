"""Which character a post uses: a mascot (an owned character with a locked
hero) is required to create a post -- the owner's newest one by default.
Posts created before that rule may have none; the image then asks for one."""
from datetime import datetime, timedelta

from app.db.models import Character
from tests.test_steps import LONG_BRIEF

API = "/api/linkedin"


def _character(api, owner, cid, hero=True, age_minutes=0):
    with api.session_factory() as s:
        s.add(Character(character_id=cid, owner_id=owner,
                        hero_image_url="https://h/x.png" if hero else None,
                        updated_at=datetime.utcnow() - timedelta(minutes=age_minutes)))
        s.commit()


def test_default_is_the_newest_character_with_a_locked_hero(api, users):
    users("user-a")
    _character(api, "user-a", "older", age_minutes=10)
    _character(api, "user-a", "newer", age_minutes=1)
    _character(api, "user-a", "no_hero", hero=False)
    _character(api, "user-b", "not_mine")
    assert api.post(f"{API}/posts", json={"brief": LONG_BRIEF}).json()["character_id"] == "newer"


def test_without_a_locked_hero_creating_a_post_is_409_character_required(api, users):
    users("fresh", with_character=False)
    _character(api, "fresh", "no_hero", hero=False)
    _character(api, "user-b", "not_mine")
    resp = api.post(f"{API}/posts", json={"brief": LONG_BRIEF})
    assert resp.status_code == 409 and resp.json()["reason"] == "character_required"
    assert api.get(f"{API}/posts").json() == []
    _character(api, "fresh", "mine")
    post = api.post(f"{API}/posts", json={"brief": LONG_BRIEF}).json()
    assert post["character_id"] == "mine" and post["active_step"]["name"] == "category"


def test_profile_required_wins_over_character_required(api, users):
    users("fresh", with_profile=False, with_character=False)
    resp = api.post(f"{API}/posts", json={"brief": LONG_BRIEF})
    assert resp.status_code == 409 and resp.json()["reason"] == "profile_required"


def test_a_requested_character_needs_a_locked_hero(api, users):
    users("user-a")
    _character(api, "user-a", "no_hero", hero=False)
    resp = api.post(f"{API}/posts", json={"brief": LONG_BRIEF, "character_id": "no_hero"})
    assert resp.status_code == 409 and resp.json()["reason"] == "character_required"


def test_a_requested_owned_locked_character_is_used(api, users):
    users("user-a")
    _character(api, "user-a", "older", age_minutes=10)
    _character(api, "user-a", "newer", age_minutes=1)
    assert api.post(f"{API}/posts", json={"brief": LONG_BRIEF, "character_id": "older"}
                    ).json()["character_id"] == "older"


def test_another_users_character_is_404(api, users):
    _character(api, "user-b", "not_mine")
    users("user-a")
    assert api.post(f"{API}/posts", json={"brief": LONG_BRIEF, "character_id": "nope"}
                    ).status_code == 404
    assert api.post(f"{API}/posts", json={"brief": LONG_BRIEF, "character_id": "not_mine"}
                    ).status_code == 404


def test_image_without_character_is_409_character_required(api, users):
    from app.db.models import Post
    users("user-a")
    with api.session_factory() as s:
        s.add(Post(id="p1", owner_id="user-a", brief="b", status="locked",
                   scene_instruction="waving", seed=1))
        s.commit()
    resp = api.post(f"{API}/posts/p1/generate-image")
    assert resp.status_code == 409 and resp.json()["reason"] == "character_required"
    _character(api, "user-a", "mine")
    assert api.patch(f"{API}/posts/p1/character", json={"character_id": "mine"}
                     ).json()["character_id"] == "mine"
    assert api.post(f"{API}/posts/p1/generate-image").json()["active_step"]["name"] == "image"


def test_picking_needs_an_owned_character_with_a_locked_hero(api, users):
    from app.db.models import Post
    users("user-a")
    with api.session_factory() as s:
        s.add(Post(id="p1", owner_id="user-a", brief="b", status="locked", seed=1))
        s.commit()
    _character(api, "user-b", "not_mine")
    _character(api, "user-a", "no_hero", hero=False)
    pick = f"{API}/posts/p1/character"
    assert api.patch(pick, json={"character_id": "not_mine"}).status_code == 404
    resp = api.patch(pick, json={"character_id": "no_hero"})
    assert resp.status_code == 409 and resp.json()["reason"] == "character_required"


def test_picking_a_character_is_409_while_the_post_is_rendering_or_busy(api, users):
    """Same rule as the other post actions: no changes mid-render/mid-step."""
    import json

    from app.db.models import Post
    users("user-a")
    _character(api, "user-a", "mine")
    _character(api, "user-a", "other")
    with api.session_factory() as s:
        s.add(Post(id="queued", owner_id="user-a", brief="b", status="image_queued",
                   scene_instruction="waving", seed=1, character_id="mine"))
        s.add(Post(id="busy", owner_id="user-a", brief="b", status="locked",
                   scene_instruction="waving", seed=1, character_id="mine",
                   active_step=json.dumps({"name": "image", "task_id": "t1",
                                           "started_at": "2026-10-17T00:00:00Z"})))
        s.commit()
    for post_id in ("queued", "busy"):
        resp = api.patch(f"{API}/posts/{post_id}/character", json={"character_id": "other"})
        assert resp.status_code == 409, post_id
    with api.session_factory() as s:
        assert s.get(Post, "queued").character_id == "mine"
        assert s.get(Post, "busy").character_id == "mine"
