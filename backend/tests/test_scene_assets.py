from app.db.models import SceneAsset
from app.services.post_service import (
    _assemble_scene_text,
    _resolve_scene_asset,
    _slugify,
    expand_scene_refs,
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
    setting_placeholder, asset_name = _resolve_scene_asset(db_session, scene)
    assert setting_placeholder == "a foggy rooftop at dusk"
    assert asset_name is None
    assert db_session.query(SceneAsset).count() == 0


def test_resolve_scene_asset_new_name_creates_asset(db_session):
    scene = {"setting_name": "Office", "setting_detail": "a bright open-plan office"}
    ref, asset_name = _resolve_scene_asset(db_session, scene)
    db_session.commit()

    assert ref == "@office"
    assert asset_name == "office"
    asset = db_session.query(SceneAsset).filter(SceneAsset.name == "office").first()
    assert asset is not None
    assert asset.detail_text == "a bright open-plan office"


def test_resolve_scene_asset_existing_name_reuses_stored_detail_not_new_proposal(db_session):
    db_session.add(SceneAsset(name="office", detail_text="the ORIGINAL office description"))
    db_session.commit()

    scene = {"setting_name": "office", "setting_detail": "a completely different proposal"}
    ref, asset_name = _resolve_scene_asset(db_session, scene)

    assert ref == "@office"
    assert asset_name == "office"
    # the existing asset's detail_text must NOT be overwritten by this call
    asset = db_session.query(SceneAsset).filter(SceneAsset.name == "office").first()
    assert asset.detail_text == "the ORIGINAL office description"


def test_resolve_scene_asset_named_but_no_detail_returns_nothing(db_session):
    scene = {"setting_name": "office", "setting_detail": None}
    assert _resolve_scene_asset(db_session, scene) == (None, None)


def test_expand_scene_refs_substitutes_current_detail_text(db_session):
    db_session.add(SceneAsset(name="office", detail_text="a bright open-plan office"))
    db_session.commit()

    expanded = expand_scene_refs(db_session, "adjusting a dial, @office, focused")
    assert expanded == "adjusting a dial, a bright open-plan office, focused"


def test_expand_scene_refs_reflects_edits_made_after_a_post_locked(db_session):
    """The whole point of the @name architecture: editing an asset's
    detail_text later must retroactively change what any post referencing it
    renders with, since expansion only ever happens at render time."""
    asset = SceneAsset(name="office", detail_text="the old description")
    db_session.add(asset)
    db_session.commit()

    asset.detail_text = "the NEW description"
    db_session.commit()

    expanded = expand_scene_refs(db_session, "waving, @office, warm")
    assert "the NEW description" in expanded
    assert "the old description" not in expanded


def test_expand_scene_refs_drops_unresolved_reference_cleanly(db_session):
    expanded = expand_scene_refs(db_session, "waving, @forgotten_asset, warm")
    assert "@forgotten_asset" not in expanded
    assert expanded == "waving, warm"


def test_expand_scene_refs_cleans_up_double_commas_and_whitespace(db_session):
    expanded = expand_scene_refs(db_session, "waving,  @missing , warm")
    assert ",," not in expanded
    assert "  " not in expanded
