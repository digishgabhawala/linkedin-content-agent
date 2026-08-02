from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from ..config import settings

engine = create_engine(f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# Columns added after the initial posts.db was already in use with real data
# (content-quality redesign, 2026-07-17) -- Base.metadata.create_all() only
# creates missing TABLES, not missing COLUMNS on an existing table, so a
# lightweight manual migration is needed to avoid dropping real locked posts.
# No formal migration tool (e.g. alembic) is set up for this single-file
# local SQLite db; a simple ADD COLUMN pass is enough at this scale.
_NEW_POST_COLUMNS = {
    "category": "TEXT",
    "gate_scores": "TEXT",
    "pillar_scores": "TEXT",
    "weighted_score": "FLOAT",
    "recalibration_count": "INTEGER NOT NULL DEFAULT 0",
    "escalation_reason": "TEXT",
    "scene_asset_name": "TEXT",
}


def _migrate_post_columns():
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(posts)"))}
        for column, coltype in _NEW_POST_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE posts ADD COLUMN {column} {coltype}"))
        conn.commit()


def init_db():
    from . import models  # noqa: F401 — ensures models are registered
    Base.metadata.create_all(bind=engine)
    _migrate_post_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
