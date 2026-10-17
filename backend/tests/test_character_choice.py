"""Which character a post uses: optional, the owner's newest locked hero by
default, required (409 character_required) only for the image."""
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


def test_without_characters_the_post_has_none_and_text_steps_run(api, users):
    users("user-a")
    post = api.post(f"{API}/posts", json={"brief": LONG_BRIEF}).json()
    assert post["character_id"] is None and post["active_step"]["name"] == "category"


def test_another_users_character_is_404(api, users):
    _character(api, "user-b", "not_mine")
    users("user-a")
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
