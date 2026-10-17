"""Per-user writer profile: API, size limits, onboarding refusal, prompts."""
from app.db.models import Post
from app.services import profile_service, steps
from tests.test_steps import LONG_BRIEF

API = "/api/linkedin"


def test_unset_profile_offers_the_template(api, users):
    users("fresh", with_profile=False)
    body = api.get(f"{API}/profile").json()
    assert body["is_set"] is False and body["profile_md"] is None
    assert body["template"] == profile_service.template() != ""


def test_save_and_read_back(api, users):
    users("fresh", with_profile=False)
    saved = api.put(f"{API}/profile", json={"profile_md": "# Asha\nPlatform engineer"}).json()
    assert saved["is_set"] is True and saved["profile_md"].startswith("# Asha")
    assert api.get(f"{API}/profile").json()["profile_md"] == "# Asha\nPlatform engineer"


def test_profile_size_limits(api, users):
    users("fresh", with_profile=False)
    assert api.put(f"{API}/profile", json={"profile_md": "x" * 8001}).status_code == 422
    assert api.put(f"{API}/profile", json={"profile_md": "   "}).status_code == 422
    assert api.put(f"{API}/profile", json={"profile_md": "x" * 8000}).status_code == 200


def test_creating_a_post_without_a_profile_is_409(api, users):
    users("fresh", with_profile=False)
    resp = api.post(f"{API}/posts", json={"brief": LONG_BRIEF})
    assert resp.status_code == 409 and resp.json()["reason"] == "profile_required"


def test_prompts_use_the_post_owners_profile(api, users):
    users("user-a", with_profile=False)
    api.put(f"{API}/profile", json={"profile_md": "UNIQUE-PROFILE-A"})
    with api.session_factory() as s:
        post = Post(owner_id="user-a", brief=LONG_BRIEF, status="drafting", post_text="t")
        s.add(post)
        s.commit()
        _, draft = steps.build(s, post, "draft", {})
        _, judge = steps.build(s, post, "judge", {})
        _, rewrite = steps.build(s, post, "rewrite", {"instruction": "shorter"})
    assert "UNIQUE-PROFILE-A" in draft.messages[0]["content"]
    assert "UNIQUE-PROFILE-A" in rewrite.messages[0]["content"]
    assert "UNIQUE-PROFILE-A" in judge.messages[1]["content"]
    assert profile_service.template()[:40] not in draft.messages[0]["content"]


def test_profiles_are_per_user(api, users):
    users("user-a", with_profile=False)
    api.put(f"{API}/profile", json={"profile_md": "A-ONLY"})
    users("user-b", with_profile=False)
    assert api.get(f"{API}/profile").json()["is_set"] is False
    users("user-a", with_profile=False)
    assert api.get(f"{API}/profile").json()["profile_md"] == "A-ONLY"
