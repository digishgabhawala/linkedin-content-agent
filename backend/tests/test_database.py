from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db import database
from app.db.database import build_engine, database_url, init_db


def test_database_url_defaults_to_sqlite_db_path(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)  # conftest forces one for safety
    assert database_url(Settings(_env_file=None, db_path="x.db")) == "sqlite:///x.db"


def test_explicit_database_url_wins():
    s = Settings(_env_file=None, database_url="postgresql+psycopg://u:p@db.example:6543/postgres")
    assert database_url(s) == "postgresql+psycopg://u:p@db.example:6543/postgres"


def test_db_schema_is_configurable():
    assert Settings(_env_file=None).db_schema == "linkedin"
    assert Settings(_env_file=None, db_schema="content_v2").db_schema == "content_v2"


def test_postgres_engine_uses_schema_map_and_pooler_safe_options(monkeypatch):
    seen = {}
    real = database.create_engine

    def spy(url, **kwargs):
        seen.update(kwargs)
        return real(url, **kwargs)

    monkeypatch.setattr(database, "create_engine", spy)
    engine = build_engine("postgresql+psycopg://u:p@db.example:6543/postgres", "content_v2")
    assert engine.get_execution_options()["schema_translate_map"] == {None: "content_v2"}
    assert seen["poolclass"] is NullPool
    assert seen["connect_args"] == {"prepare_threshold": None}


def test_sqlite_engine_has_no_schema_map():
    engine = build_engine("sqlite:///:memory:", "linkedin")
    assert "schema_translate_map" not in engine.get_execution_options()


def test_init_db_adds_columns_missing_from_an_old_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # a posts table from before later columns existed
        conn.execute(text("CREATE TABLE posts (id VARCHAR PRIMARY KEY, character_id VARCHAR, "
                          "brief TEXT, status VARCHAR, draft_version INTEGER)"))
        conn.execute(text("CREATE TABLE characters (character_id VARCHAR PRIMARY KEY, "
                          "display_name VARCHAR, hero_image_url VARCHAR, updated_at DATETIME)"))
        conn.execute(text("CREATE TABLE hero_candidates (id VARCHAR PRIMARY KEY)"))
    init_db(engine, "linkedin")
    columns = {c["name"] for c in inspect(engine).get_columns("posts")}
    assert {"image_profile", "image_task_id", "recalibration_count",
            "scene_asset_version_id"} <= columns
    character_columns = {c["name"] for c in inspect(engine).get_columns("characters")}
    assert {"card_json", "hero_asset_id", "hero_version",
            "hero_candidate_id"} <= character_columns
    candidate_columns = {c["name"] for c in inspect(engine).get_columns("hero_candidates")}
    assert "selected_at" in candidate_columns
    scene_columns = {c["name"] for c in inspect(engine).get_columns("scene_assets")}
    assert {"current_version", "display_name", "archived_at"} <= scene_columns
    assert {"post_drafts", "scene_assets", "scene_asset_versions", "feedback",
            "hero_generation_runs", "hero_candidates"} <= set(
                inspect(engine).get_table_names())


def test_init_db_backfills_scene_asset_v1_and_pins_legacy_posts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-scenes.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE scene_assets (id VARCHAR PRIMARY KEY, name VARCHAR UNIQUE, "
            "detail_text TEXT, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text(
            "INSERT INTO scene_assets (id, name, detail_text) "
            "VALUES ('asset-1', 'office', 'the original office')"))
        conn.execute(text(
            "CREATE TABLE posts (id VARCHAR PRIMARY KEY, character_id VARCHAR, brief TEXT, "
            "status VARCHAR, draft_version INTEGER, scene_asset_name VARCHAR)"))
        conn.execute(text(
            "INSERT INTO posts (id, brief, status, draft_version, scene_asset_name) "
            "VALUES ('post-1', 'b', 'locked', 0, 'office')"))
        conn.execute(text(
            "CREATE TABLE characters (character_id VARCHAR PRIMARY KEY, display_name VARCHAR, "
            "hero_image_url VARCHAR, updated_at DATETIME)"))
        conn.execute(text("CREATE TABLE hero_candidates (id VARCHAR PRIMARY KEY)"))

    init_db(engine, "linkedin")

    with engine.connect() as conn:
        version = conn.execute(text(
            "SELECT id, version, detail_text FROM scene_asset_versions "
            "WHERE scene_asset_name = 'office'"))
        row = version.mappings().one()
        pinned = conn.execute(text(
            "SELECT scene_asset_version_id FROM posts WHERE id = 'post-1'"
        )).scalar_one()
        display_name = conn.execute(text(
            "SELECT display_name FROM scene_assets WHERE name = 'office'"
        )).scalar_one()
    assert row["version"] == 1
    assert row["detail_text"] == "the original office"
    assert pinned == row["id"]
    assert display_name == "Office"
