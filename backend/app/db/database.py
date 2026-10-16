"""Database engine, session and schema setup.

The location (DATABASE_URL) and the Postgres schema (DB_SCHEMA) are
configuration: models and queries never name a schema -- SQLAlchemy's
schema_translate_map applies it -- so moving to another project/schema is a
config change plus a data copy (see app/db/copy.py).
"""
import uuid

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from ..config import Settings, settings


def database_url(s: Settings = settings) -> str:
    return s.database_url or f"sqlite:///{s.db_path}"


def build_engine(url: str, schema: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # Supabase's transaction pooler (port 6543) multiplexes connections, so
    # no app-side pooling and no server-side prepared statements -- the same
    # settings task-queue's db.py had to adopt.
    engine = create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})
    return engine.execution_options(schema_translate_map={None: schema})


engine = build_engine(database_url(), settings.db_schema)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# Columns added to `posts` after the first databases held real data:
# create_all() creates missing TABLES, not missing COLUMNS, so add them here.
# Types must be valid on both SQLite and Postgres. No migration framework --
# a simple ADD COLUMN pass is enough at this scale.
_NEW_POST_COLUMNS = {
    "category": "TEXT",
    "gate_scores": "TEXT",
    "pillar_scores": "TEXT",
    "weighted_score": "FLOAT",
    "recalibration_count": "INTEGER NOT NULL DEFAULT 0",
    "escalation_reason": "TEXT",
    "scene_asset_name": "TEXT",
    "scene_asset_version_id": "TEXT",
    "image_task_id": "TEXT",
    "image_profile": "TEXT",
    "active_step": "TEXT",
    "step_context": "TEXT",
    "step_error": "TEXT",
}

_NEW_CHARACTER_COLUMNS = {
    "card_json": "TEXT",
    "hero_asset_id": "TEXT",
    "hero_version": "INTEGER NOT NULL DEFAULT 0",
    "hero_candidate_id": "TEXT",
}

_NEW_HERO_CANDIDATE_COLUMNS = {
    "selected_at": "TIMESTAMP",
}

_NEW_SCENE_ASSET_COLUMNS = {
    "current_version": "INTEGER NOT NULL DEFAULT 1",
    "display_name": "TEXT",
    "archived_at": "TIMESTAMP",
}


def _add_missing_post_columns(bind: Engine, schema: str) -> None:
    postgres = bind.dialect.name == "postgresql"
    existing = {c["name"] for c in
                inspect(bind).get_columns("posts", schema=schema if postgres else None)}
    # Raw DDL isn't schema-translated, so qualify the table name explicitly.
    table = f'"{schema}".posts' if postgres else "posts"
    with bind.begin() as conn:
        for column, coltype in _NEW_POST_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _add_missing_character_columns(bind: Engine, schema: str) -> None:
    postgres = bind.dialect.name == "postgresql"
    existing = {c["name"] for c in
                inspect(bind).get_columns("characters", schema=schema if postgres else None)}
    table = f'"{schema}".characters' if postgres else "characters"
    with bind.begin() as conn:
        for column, coltype in _NEW_CHARACTER_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _add_missing_hero_candidate_columns(bind: Engine, schema: str) -> None:
    postgres = bind.dialect.name == "postgresql"
    inspector = inspect(bind)
    tables = set(inspector.get_table_names(schema=schema if postgres else None))
    if "hero_candidates" not in tables:
        return
    existing = {c["name"] for c in inspector.get_columns(
        "hero_candidates", schema=schema if postgres else None)}
    table = f'"{schema}".hero_candidates' if postgres else "hero_candidates"
    with bind.begin() as conn:
        for column, coltype in _NEW_HERO_CANDIDATE_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _add_missing_scene_asset_columns(bind: Engine, schema: str) -> None:
    postgres = bind.dialect.name == "postgresql"
    existing = {c["name"] for c in inspect(bind).get_columns(
        "scene_assets", schema=schema if postgres else None)}
    table = f'"{schema}".scene_assets' if postgres else "scene_assets"
    with bind.begin() as conn:
        for column, coltype in _NEW_SCENE_ASSET_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _backfill_scene_asset_versions(bind: Engine, schema: str) -> None:
    """Turn every pre-versioning backdrop into v1 and pin legacy posts.

    Core statements select only columns guaranteed to exist, which keeps the
    lightweight old-schema migration tests valid as well as production.
    """
    from .models import Post, SceneAsset, SceneAssetVersion

    assets = SceneAsset.__table__
    versions = SceneAssetVersion.__table__
    posts = Post.__table__
    post_table = f'"{schema}".posts' if bind.dialect.name == "postgresql" else "posts"
    with bind.begin() as conn:
        rows = conn.execute(select(
            assets.c.name, assets.c.detail_text, assets.c.current_version,
        )).mappings().all()
        version_ids: dict[str, str] = {}
        for row in rows:
            existing = conn.execute(select(versions.c.id).where(
                versions.c.scene_asset_name == row["name"],
                versions.c.version == row["current_version"],
            )).scalar_one_or_none()
            version_id = existing or str(uuid.uuid4())
            if existing is None:
                conn.execute(versions.insert().values(
                    id=version_id,
                    scene_asset_name=row["name"],
                    version=row["current_version"],
                    detail_text=row["detail_text"],
                ))
            version_ids[row["name"]] = version_id

        legacy_posts = conn.execute(select(posts.c.id, posts.c.scene_asset_name).where(
            posts.c.scene_asset_name.is_not(None),
            posts.c.scene_asset_version_id.is_(None),
        )).mappings().all()
        for post in legacy_posts:
            version_id = version_ids.get(post["scene_asset_name"])
            if version_id:
                conn.execute(text(
                    f"UPDATE {post_table} SET scene_asset_version_id = :version_id "
                    "WHERE id = :post_id"
                ), {"version_id": version_id, "post_id": post["id"]})


def _backfill_scene_asset_display_names(bind: Engine) -> None:
    """Give legacy backdrop slugs a readable label without changing their IDs."""
    from .models import SceneAsset

    assets = SceneAsset.__table__
    with bind.begin() as conn:
        rows = conn.execute(select(
            assets.c.id, assets.c.name, assets.c.display_name,
        )).mappings().all()
        for row in rows:
            if row["display_name"]:
                continue
            words = row["name"].replace("_", " ").strip()
            conn.execute(
                assets.update().where(assets.c.id == row["id"]).values(
                    display_name=words[:1].upper() + words[1:]),
            )


def init_db(bind: Engine = engine, schema: str = settings.db_schema) -> None:
    from . import models  # noqa: F401 — ensures models are registered
    if bind.dialect.name == "postgresql":
        with bind.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=bind)
    _add_missing_post_columns(bind, schema)
    _add_missing_character_columns(bind, schema)
    _add_missing_hero_candidate_columns(bind, schema)
    _add_missing_scene_asset_columns(bind, schema)
    _backfill_scene_asset_versions(bind, schema)
    _backfill_scene_asset_display_names(bind)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
