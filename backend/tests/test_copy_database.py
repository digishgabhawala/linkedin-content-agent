from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import LOCAL_USER_ID
from app.db.copy import TargetNotEmpty, copy_database
from app.db.database import build_engine, init_db
from app.db.models import (
    Character,
    Feedback,
    HeroCandidate,
    HeroGenerationRun,
    Post,
    PostDraft,
    SceneAsset,
    SceneAssetVersion,
)


def _seed(url):
    engine = build_engine(url, "linkedin")
    init_db(engine, "linkedin")
    with Session(engine) as s:
        post = Post(owner_id=LOCAL_USER_ID, id="p1", character_id="gtee_dev", brief="brief", status="image_ready",
                    image_profile="lightning", final_image_path="https://x/y.png",
                    scene_asset_name="office", scene_asset_version_id="sv1",
                    created_at=datetime(2026, 10, 1, 9, 30))  # noqa: DTZ001 -- naive UTC, like every DB column
        run = HeroGenerationRun(
            id="r1", character_id="gtee_dev", card_json='{"character_id":"gtee_dev"}',
            profile="full", base_seed=1000, requested_candidates=1, status="completed")
        s.add_all([Character(character_id="gtee_dev", personality="dry humor"),
                   run, HeroCandidate(id="h1", run_id="r1", task_id="t1", seed=1000,
                                      status="ready", image_url="https://x/hero.png"), post,
                   SceneAsset(id="s1", name="office", detail_text="a desk"),
                   SceneAssetVersion(id="sv1", scene_asset_name="office", version=1,
                                     detail_text="a desk"),
                   PostDraft(id="d1", post_id="p1", version=1, post_text="hello",
                             generated_by="draft"),
                   Feedback(id="f1", post_id="p1", stage="draft", user_note="nice")])
        s.commit()


def test_copies_every_table_preserving_ids_and_values(tmp_path):
    source, target = f"sqlite:///{tmp_path / 'src.db'}", f"sqlite:///{tmp_path / 'dst.db'}"
    _seed(source)

    counts = copy_database(source, target, "linkedin")

    assert counts == {"characters": 1, "hero_generation_runs": 1, "hero_candidates": 1,
                      "scene_assets": 1, "scene_asset_versions": 1, "posts": 1,
                      "post_drafts": 1, "feedback": 1}
    with Session(build_engine(target, "linkedin")) as s:
        post = s.get(Post, "p1")
        assert post.image_profile == "lightning"
        assert post.final_image_path == "https://x/y.png"
        assert post.created_at == datetime(2026, 10, 1, 9, 30)  # noqa: DTZ001
        assert s.scalars(select(PostDraft.post_id)).all() == ["p1"]
        assert s.get(SceneAsset, "s1").name == "office"
        assert post.backdrop_version.detail_text == "a desk"
        assert post.character.personality == "dry humor"
        assert s.get(HeroGenerationRun, "r1").candidates[0].image_url == "https://x/hero.png"


def test_refuses_to_copy_into_a_target_that_has_data(tmp_path):
    source, target = f"sqlite:///{tmp_path / 'src.db'}", f"sqlite:///{tmp_path / 'dst.db'}"
    _seed(source)
    copy_database(source, target, "linkedin")
    with pytest.raises(TargetNotEmpty, match="already has 1 rows"):
        copy_database(source, target, "linkedin")
