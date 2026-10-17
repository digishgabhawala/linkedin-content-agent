import pytest

from app.auth import LOCAL_USER_ID
from app.db.models import Post, SceneAsset, SceneAssetVersion
from app.services.post_service import (
    PostServiceError,
    _assemble_scene_text,
    _current_scene_asset_version,
    _resolve_scene_asset,
    _slugify,
    archive_scene_asset,
    create_scene_asset,
    expand_scene_refs,
    list_scene_assets,
    restore_scene_asset_version,
    set_post_scene_asset,
    unarchive_scene_asset,
    update_scene,
    update_scene_asset,
    use_latest_scene_asset,
)


def test_slugify_lowercases_and_replaces_non_alnum():
    assert _slugify("Coffee Shop!") == "coffee_shop"
    assert _slugify("  Home Desk  ") == "home_desk"
    assert _slugify("office") == "office"


def test_assemble_scene_text_joins_non_empty_parts_with_setting():
    scene = {"action": "adjusting a dial", "angle": "side view", "mood": "focused"}
    text = _assemble_scene_text(scene, "a cluttered home desk")
    assert text == "adjusting a dial, a cluttered home desk, side view, focused"


def test_assemble_scene_text_drops_setting_when_none():
    scene = {"action": "waving hello", "angle": "front view", "mood": "warm"}
    assert _assemble_scene_text(scene, None) == "waving hello, front view, warm"


def test_resolve_scene_asset_no_name_passes_through_raw_detail(db_session):
    scene = {"setting_name": None, "setting_detail": "a foggy rooftop at dusk"}
    setting_placeholder, asset_name, version_id = _resolve_scene_asset(db_session, scene, owner_id=LOCAL_USER_ID)
    assert setting_placeholder == "a foggy rooftop at dusk"
    assert asset_name is None
    assert version_id is None
    assert db_session.query(SceneAsset).count() == 0


def test_resolve_scene_asset_new_name_creates_asset(db_session):
    scene = {"setting_name": "Office", "setting_detail": "a bright open-plan office"}
    ref, asset_name, version_id = _resolve_scene_asset(db_session, scene, owner_id=LOCAL_USER_ID)
    db_session.commit()

    assert ref == "@office"
    assert asset_name == "office"
    asset = db_session.query(SceneAsset).filter(SceneAsset.name == "office").first()
    assert asset is not None
    assert asset.detail_text == "a bright open-plan office"
    assert asset.current_version == 1
    assert db_session.get(SceneAssetVersion, version_id).detail_text == asset.detail_text


def test_resolve_scene_asset_existing_name_reuses_stored_detail_not_new_proposal(db_session):
    db_session.add(SceneAsset(owner_id=LOCAL_USER_ID, name="office", detail_text="the ORIGINAL office description"))
    db_session.commit()

    scene = {"setting_name": "office", "setting_detail": "a completely different proposal"}
    ref, asset_name, version_id = _resolve_scene_asset(db_session, scene, owner_id=LOCAL_USER_ID)

    assert ref == "@office"
    assert asset_name == "office"
    # the existing asset's detail_text must NOT be overwritten by this call
    asset = db_session.query(SceneAsset).filter(SceneAsset.name == "office").first()
    assert asset.detail_text == "the ORIGINAL office description"
    assert db_session.get(SceneAssetVersion, version_id).version == 1


def test_resolve_scene_asset_named_but_no_detail_returns_nothing(db_session):
    scene = {"setting_name": "office", "setting_detail": None}
    assert _resolve_scene_asset(db_session, scene, owner_id=LOCAL_USER_ID) == (None, None, None)


def test_expand_scene_refs_substitutes_current_detail_text(db_session):
    db_session.add(SceneAsset(owner_id=LOCAL_USER_ID, name="office", detail_text="a bright open-plan office"))
    db_session.commit()

    expanded = expand_scene_refs(db_session, "adjusting a dial, @office, focused", owner_id=LOCAL_USER_ID)
    assert expanded == "adjusting a dial, a bright open-plan office, focused"


def test_expand_scene_refs_keeps_a_posts_pinned_historical_version(db_session):
    asset = SceneAsset(owner_id=LOCAL_USER_ID, name="office", detail_text="the old description")
    db_session.add(asset)
    db_session.commit()
    old_version = _resolve_scene_asset(db_session, {
        "setting_name": "office", "setting_detail": "ignored",
    }, owner_id=LOCAL_USER_ID)[2]

    update_scene_asset(db_session, "office", "the NEW description", owner_id=LOCAL_USER_ID)

    expanded = expand_scene_refs(
        db_session, "waving, @office, warm", "office", old_version, owner_id=LOCAL_USER_ID)
    assert "the old description" in expanded
    assert "the NEW description" not in expanded


def test_unpinned_scene_ref_uses_current_version(db_session):
    db_session.add(SceneAsset(owner_id=LOCAL_USER_ID, name="office", detail_text="the old description"))
    db_session.commit()
    update_scene_asset(db_session, "office", "the NEW description", owner_id=LOCAL_USER_ID)

    assert "the NEW description" in expand_scene_refs(
        db_session, "waving, @office, warm", owner_id=LOCAL_USER_ID)


def test_editing_asset_appends_immutable_version(db_session):
    _resolve_scene_asset(db_session, {
        "setting_name": "office", "setting_detail": "v1 description",
    }, owner_id=LOCAL_USER_ID)
    db_session.commit()

    asset = update_scene_asset(db_session, "office", "v2 description", owner_id=LOCAL_USER_ID)
    versions = db_session.query(SceneAssetVersion).order_by(SceneAssetVersion.version).all()

    assert asset.current_version == 2
    assert [(v.version, v.detail_text) for v in versions] == [
        (1, "v1 description"), (2, "v2 description")]


def test_manual_scene_reference_is_pinned_and_can_explicitly_use_latest(db_session):
    _, _, v1_id = _resolve_scene_asset(db_session, {
        "setting_name": "office", "setting_detail": "v1 description",
    }, owner_id=LOCAL_USER_ID)
    post = Post(owner_id=LOCAL_USER_ID, brief="b", status="locked", scene_instruction="standing")
    db_session.add(post)
    db_session.commit()

    update_scene(db_session, post.id, "standing, @office, focused")
    assert post.scene_asset_name == "office"
    assert post.scene_asset_version_id == v1_id

    update_scene_asset(db_session, "office", "v2 description", owner_id=LOCAL_USER_ID)
    assert "v1 description" in expand_scene_refs(
        db_session, post.scene_instruction, post.scene_asset_name,
        post.scene_asset_version_id, owner_id=LOCAL_USER_ID)

    use_latest_scene_asset(db_session, post.id)
    assert db_session.get(SceneAssetVersion, post.scene_asset_version_id).version == 2
    assert post.status == "locked"


def test_scene_edit_after_render_requires_a_fresh_render(db_session):
    post = Post(
        owner_id=LOCAL_USER_ID,
        brief="b", status="image_ready", scene_instruction="standing",
        final_image_path="https://example.test/old.png",
    )
    db_session.add(post)
    db_session.commit()

    updated = update_scene(db_session, post.id, "sitting by a window")

    assert updated.status == "locked"
    assert updated.scene_instruction == "sitting by a window"


def test_archiving_asset_keeps_history_and_stops_automatic_reuse(db_session):
    _, _, v1_id = _resolve_scene_asset(db_session, {
        "setting_name": "office", "setting_detail": "v1 description",
    }, owner_id=LOCAL_USER_ID)
    db_session.commit()
    archived = archive_scene_asset(db_session, "office", owner_id=LOCAL_USER_ID)

    assert archived.archived_at is not None
    assert "v1 description" in expand_scene_refs(
        db_session, "standing, @office", "office", v1_id, owner_id=LOCAL_USER_ID)

    assert _resolve_scene_asset(db_session, {
        "setting_name": "office", "setting_detail": "fresh description",
    }, owner_id=LOCAL_USER_ID) == ("fresh description", None, None)

    restored = unarchive_scene_asset(db_session, "office", owner_id=LOCAL_USER_ID)
    assert restored.archived_at is None
    assert restored.current_version == 1


def test_manual_creation_and_historical_restore_append_versions(db_session):
    asset = create_scene_asset(db_session, "Home Desk", "first description", owner_id=LOCAL_USER_ID)
    assert asset.name == "home_desk"
    assert asset.display_name == "Home Desk"
    assert asset.current_version == 1

    update_scene_asset(db_session, "home_desk", "second description", "My Desk", owner_id=LOCAL_USER_ID)
    restored = restore_scene_asset_version(db_session, "home_desk", 1, owner_id=LOCAL_USER_ID)
    assert restored.display_name == "My Desk"
    assert restored.detail_text == "first description"
    assert restored.current_version == 3
    assert [(v.version, v.detail_text) for v in db_session.query(
        SceneAssetVersion).order_by(SceneAssetVersion.version).all()] == [
            (1, "first description"),
            (2, "second description"),
            (3, "first description"),
        ]


def test_selecting_and_clearing_post_backdrop_updates_scene_and_pin(db_session):
    create_scene_asset(db_session, "Home Desk", "a focused desk", owner_id=LOCAL_USER_ID)
    post = Post(
        owner_id=LOCAL_USER_ID,
        brief="b", status="image_ready",
        scene_instruction="reviewing notes, @office, focused",
        scene_asset_name="office",
    )
    db_session.add(post)
    db_session.commit()

    selected = set_post_scene_asset(db_session, post.id, "home_desk")
    assert selected.status == "locked"
    assert selected.scene_asset_name == "home_desk"
    assert selected.scene_instruction == "reviewing notes, focused, @home_desk"
    assert db_session.get(SceneAssetVersion, selected.scene_asset_version_id).version == 1

    cleared = set_post_scene_asset(db_session, post.id, None)
    assert cleared.scene_asset_name is None
    assert cleared.scene_asset_version_id is None
    assert cleared.scene_instruction == "reviewing notes, focused"


def test_expand_scene_refs_drops_unresolved_reference_cleanly(db_session):
    expanded = expand_scene_refs(db_session, "waving, @forgotten_asset, warm", owner_id=LOCAL_USER_ID)
    assert "@forgotten_asset" not in expanded
    assert expanded == "waving, warm"


def test_expand_scene_refs_cleans_up_double_commas_and_whitespace(db_session):
    expanded = expand_scene_refs(db_session, "waving,  @missing , warm", owner_id=LOCAL_USER_ID)
    assert ",," not in expanded
    assert "  " not in expanded


def test_two_owners_can_each_have_an_office_backdrop(db_session):
    a = create_scene_asset(db_session, "Office", "A's office", owner_id="user-a")
    b = create_scene_asset(db_session, "Office", "B's office", owner_id="user-b")
    assert a.name == b.name == "office"
    assert [x.detail_text for x in list_scene_assets(db_session, owner_id="user-b")] == ["B's office"]


def test_scene_refs_expand_with_the_post_owners_backdrop(db_session):
    create_scene_asset(db_session, "Office", "A's office", owner_id="user-a")
    create_scene_asset(db_session, "Office", "B's office", owner_id="user-b")
    assert expand_scene_refs(db_session, "typing, @office", owner_id="user-b") == "typing, B's office"


def test_pinned_version_of_another_owner_is_not_found(db_session):
    a = create_scene_asset(db_session, "Office", "A's office", owner_id="user-a")
    version_id = _current_scene_asset_version(db_session, a).id
    with pytest.raises(PostServiceError, match="not found"):
        expand_scene_refs(db_session, "x, @office", "office", version_id, owner_id="user-b")


def test_scene_agent_creates_backdrops_for_the_post_owner_only(db_session):
    create_scene_asset(db_session, "Office", "A's office", owner_id="user-a")
    placeholder, name, version_id = _resolve_scene_asset(
        db_session, {"setting_name": "office", "setting_detail": "B's new office"},
        owner_id="user-b")
    version = db_session.get(SceneAssetVersion, version_id)
    assert (placeholder, name, version.owner_id, version.detail_text) == (
        "@office", "office", "user-b", "B's new office")


def test_post_backdrop_relationship_is_owner_scoped(db_session):
    create_scene_asset(db_session, "Office", "A's office", owner_id="user-a")
    create_scene_asset(db_session, "Office", "B's office", owner_id="user-b")
    post = Post(owner_id="user-b", brief="b", status="locked", scene_asset_name="office")
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    assert post.scene_asset.detail_text == "B's office"
