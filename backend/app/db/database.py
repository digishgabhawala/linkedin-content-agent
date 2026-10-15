"""Database engine, session and schema setup.

The location (DATABASE_URL) and the Postgres schema (DB_SCHEMA) are
configuration: models and queries never name a schema -- SQLAlchemy's
schema_translate_map applies it -- so moving to another project/schema is a
config change plus a data copy (see app/db/copy.py).
"""
from sqlalchemy import create_engine, inspect, text
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


def init_db(bind: Engine = engine, schema: str = settings.db_schema) -> None:
    from . import models  # noqa: F401 — ensures models are registered
    if bind.dialect.name == "postgresql":
        with bind.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=bind)
    _add_missing_post_columns(bind, schema)
    _add_missing_character_columns(bind, schema)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
