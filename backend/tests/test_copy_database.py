from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.copy import TargetNotEmpty, copy_database
from app.db.database import build_engine, init_db
from app.db.models import Feedback, Post, PostDraft, SceneAsset


def _seed(url):
    engine = build_engine(url, "linkedin")
    init_db(engine, "linkedin")
    with Session(engine) as s:
        post = Post(id="p1", character_id="gtee_dev", brief="brief", status="image_ready",
                    image_profile="lightning", final_image_path="https://x/y.png",
                    created_at=datetime(2026, 10, 1, 9, 30))  # noqa: DTZ001 -- naive UTC, like every DB column
        s.add_all([post,
                   SceneAsset(id="s1", name="office", detail_text="a desk"),
                   PostDraft(id="d1", post_id="p1", version=1, post_text="hello",
                             generated_by="draft"),
                   Feedback(id="f1", post_id="p1", stage="draft", user_note="nice")])
        s.commit()


def test_copies_every_table_preserving_ids_and_values(tmp_path):
    source, target = f"sqlite:///{tmp_path / 'src.db'}", f"sqlite:///{tmp_path / 'dst.db'}"
    _seed(source)

    counts = copy_database(source, target, "linkedin")

    assert counts == {"posts": 1, "scene_assets": 1, "post_drafts": 1, "feedback": 1}
    with Session(build_engine(target, "linkedin")) as s:
        post = s.get(Post, "p1")
        assert post.image_profile == "lightning"
        assert post.final_image_path == "https://x/y.png"
        assert post.created_at == datetime(2026, 10, 1, 9, 30)  # noqa: DTZ001
        assert s.scalars(select(PostDraft.post_id)).all() == ["p1"]
        assert s.get(SceneAsset, "s1").name == "office"


def test_refuses_to_copy_into_a_target_that_has_data(tmp_path):
    source, target = f"sqlite:///{tmp_path / 'src.db'}", f"sqlite:///{tmp_path / 'dst.db'}"
    _seed(source)
    copy_database(source, target, "linkedin")
    with pytest.raises(TargetNotEmpty, match="posts"):
        copy_database(source, target, "linkedin")
