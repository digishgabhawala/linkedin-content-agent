"""One-off data copy between databases (e.g. local SQLite -> Supabase).

Copies every table in foreign-key order, preserving primary keys and all
column values, in one transaction. Refuses to touch a target that already
has rows -- no duplicate or merge logic. The source is only read.
"""
from __future__ import annotations

from sqlalchemy import func, select

from . import models
from .database import build_engine, init_db

# Parents before children (candidates reference runs; drafts/feedback reference posts).
TABLES = [models.Character.__table__, models.HeroGenerationRun.__table__,
          models.HeroCandidate.__table__, models.SceneAsset.__table__,
          models.SceneAssetVersion.__table__, models.Post.__table__, models.PostDraft.__table__,
          models.Feedback.__table__]


class TargetNotEmpty(RuntimeError):
    pass


def copy_database(source_url: str, target_url: str, schema: str) -> dict[str, int]:
    source = build_engine(source_url, schema)
    target = build_engine(target_url, schema)
    init_db(target, schema)  # schema, tables and columns exist before copying

    counts: dict[str, int] = {}
    with target.begin() as dst, source.connect() as src:
        for table in TABLES:
            existing = dst.execute(select(func.count()).select_from(table)).scalar()
            if existing:
                raise TargetNotEmpty(f"target table {table.name} already has {existing} rows")
        for table in TABLES:
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            if rows:
                dst.execute(table.insert(), rows)
            counts[table.name] = len(rows)
    return counts
