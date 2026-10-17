from app.auth import LOCAL_USER_ID
from app.db.database import get_db
from app.db.models import Post
from app.main import app
from app.services.post_service import _resolve_scene_asset


def _post_pinned_to_office(api) -> str:
    session = next(app.dependency_overrides[get_db]())
    _, _, version_id = _resolve_scene_asset(session, {
        "setting_name": "office",
        "setting_detail": "a bright open-plan office",
    }, owner_id=LOCAL_USER_ID)
    post = Post(
        owner_id=LOCAL_USER_ID,
        brief="A useful post",
        status="image_ready",
        scene_instruction="reviewing notes, @office, focused",
        scene_asset_name="office",
        scene_asset_version_id=version_id,
    )
    session.add(post)
    session.commit()
    return post.id


def test_scene_asset_routes_expose_history_and_explicit_latest_upgrade(api):
    post_id = _post_pinned_to_office(api)

    asset = api.patch(
        "/api/linkedin/scene-assets/office",
        json={"detail_text": "a quiet private office"},
    ).json()
    assert asset["current_version"] == 2

    history = api.get("/api/linkedin/scene-assets/office/versions").json()
    assert [(item["version"], item["detail_text"]) for item in history] == [
        (2, "a quiet private office"),
        (1, "a bright open-plan office"),
    ]
    assert history[1]["usage_count"] == 1
    assert history[1]["posts"][0]["id"] == post_id

    before = api.get(f"/api/linkedin/posts/{post_id}").json()
    assert before["scene_asset_version"] == 1
    assert before["scene_asset_latest_version"] == 2
    assert before["scene_asset_is_latest"] is False

    after = api.post(
        f"/api/linkedin/posts/{post_id}/scene/use-latest-backdrop"
    ).json()
    assert after["scene_asset_version"] == 2
    assert after["scene_asset_is_latest"] is True
    assert after["status"] == "locked"


def test_backdrop_library_create_archive_restore_and_post_selection(api):
    post_id = _post_pinned_to_office(api)
    created_response = api.post(
        "/api/linkedin/scene-assets",
        json={"display_name": "Home Desk", "detail_text": "a warm focused desk"},
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "home_desk"
    assert created["display_name"] == "Home Desk"
    assert created["usage_count"] == 0

    selected = api.patch(
        f"/api/linkedin/posts/{post_id}/backdrop",
        json={"scene_asset_name": "home_desk"},
    ).json()
    assert selected["scene_asset_name"] == "home_desk"
    assert selected["scene_asset_display_name"] == "Home Desk"
    assert "@home_desk" in selected["scene_instruction"]
    assert "@office" not in selected["scene_instruction"]
    assert selected["status"] == "locked"

    archived = api.post("/api/linkedin/scene-assets/home_desk/archive").json()
    assert archived["archived_at"] is not None
    assert all(item["name"] != "home_desk" for item in api.get(
        "/api/linkedin/scene-assets").json())
    assert any(item["name"] == "home_desk" for item in api.get(
        "/api/linkedin/scene-assets?include_archived=true").json())

    restored = api.post("/api/linkedin/scene-assets/home_desk/unarchive").json()
    assert restored["archived_at"] is None

    api.patch(
        "/api/linkedin/scene-assets/home_desk",
        json={"display_name": "My Home Desk", "detail_text": "a cooler desk"},
    )
    historical = api.post(
        "/api/linkedin/scene-assets/home_desk/versions/1/restore"
    ).json()
    assert historical["current_version"] == 3
    assert historical["detail_text"] == "a warm focused desk"

