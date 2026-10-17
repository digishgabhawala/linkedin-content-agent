"""One-off data copy between databases (e.g. local SQLite -> Supabase).

Copies every table in foreign-key order, preserving primary keys and all
column values, in one transaction. Refuses to touch a target that already
has rows -- no duplicate or merge logic. The source is only read.

One exception: init_db seeds the backfill owner's writer profile from the
template (content_config/user_profile.md). That seed is not user data, so it
doesn't count as "already has rows" and the source's profile replaces it.
"""
from __future__ import annotations

from sqlalchemy import func, select

from ..agents.content_sources import load_user_profile
from . import models
from .database import build_engine, init_db

# Parents before children (candidates reference runs; posts reference backdrop
# versions; drafts/feedback reference posts). writer_profiles has no FKs.
TABLES = [models.Character.__table__, models.HeroGenerationRun.__table__,
          models.HeroCandidate.__table__, models.SceneAsset.__table__,
          models.SceneAssetVersion.__table__, models.Post.__table__, models.PostDraft.__table__,
          models.Feedback.__table__, models.WriterProfile.__table__]
_PROFILES = models.WriterProfile.__table__


class TargetNotEmpty(RuntimeError):
    pass


def copy_database(source_url: str, target_url: str, schema: str) -> dict[str, int]:
    source = build_engine(source_url, schema)
    target = build_engine(target_url, schema)
    init_db(target, schema)  # schema, tables and columns exist before copying

    counts: dict[str, int] = {}
    with target.begin() as dst, source.connect() as src:
        seed = load_user_profile()
        for table in TABLES:
            query = select(func.count()).select_from(table)
            if table is _PROFILES:  # the template seed from init_db isn't user data
                query = query.where(_PROFILES.c.profile_md != seed)
            existing = dst.execute(query).scalar()
            if existing:
                raise TargetNotEmpty(f"target table {table.name} already has {existing} rows")
        for table in TABLES:
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            if rows and table is _PROFILES:
                dst.execute(_PROFILES.delete().where(
                    _PROFILES.c.owner_id.in_([r["owner_id"] for r in rows])))
            if rows:
                dst.execute(table.insert(), rows)
            counts[table.name] = len(rows)
    return counts
