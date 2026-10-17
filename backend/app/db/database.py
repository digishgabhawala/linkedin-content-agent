"""Database engine, session and schema setup.

The location (DATABASE_URL) and the Postgres schema (DB_SCHEMA) are
configuration: models and queries never name a schema -- SQLAlchemy's
schema_translate_map applies it -- so moving to another project/schema is a
config change plus a data copy (see app/db/copy.py).
"""
import uuid
from datetime import datetime

from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from ..config import Settings, settings
from . import owners


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
    "owner_id": "TEXT",
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
    "owner_id": "TEXT",
    "card_json": "TEXT",
    "hero_asset_id": "TEXT",
    "hero_version": "INTEGER NOT NULL DEFAULT 0",
    "hero_candidate_id": "TEXT",
}

_NEW_HERO_CANDIDATE_COLUMNS = {
    "selected_at": "TIMESTAMP",
}

_NEW_SCENE_ASSET_COLUMNS = {
    "owner_id": "TEXT",
    "current_version": "INTEGER NOT NULL DEFAULT 1",
    "display_name": "TEXT",
    "archived_at": "TIMESTAMP",
}


_NEW_SCENE_ASSET_VERSION_COLUMNS = {
    "owner_id": "TEXT",
}

_COLUMNS_BY_TABLE = {"posts": _NEW_POST_COLUMNS, "characters": _NEW_CHARACTER_COLUMNS,
                "hero_candidates": _NEW_HERO_CANDIDATE_COLUMNS,
                "scene_assets": _NEW_SCENE_ASSET_COLUMNS,
                "scene_asset_versions": _NEW_SCENE_ASSET_VERSION_COLUMNS}

# Tables whose rows belong to a user directly (drafts, feedback and hero runs
# belong through their post / character).
_OWNED_TABLES = ("posts", "scene_assets", "scene_asset_versions", "characters")


def _postgres(bind: Engine) -> bool:
    return bind.dialect.name == "postgresql"


def _set_lock_timeout(conn, bind: Engine) -> None:
    """Postgres DDL in a migration transaction gives up after _LOCK_TIMEOUT
    instead of waiting behind the still-serving old app (a waiting ALTER makes
    every later query on that table wait too). Re-running finishes the job."""
    if _postgres(bind):
        conn.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))


def _q(bind: Engine, schema: str, table: str) -> str:
    """Raw DDL/SQL isn't schema-translated, so qualify the table explicitly."""
    return f'"{schema}".{table}' if _postgres(bind) else table


def _reflect_schema(bind: Engine, schema: str) -> str | None:
    return schema if _postgres(bind) else None


def _add_missing_columns(bind: Engine, schema: str, table: str, columns: dict[str, str]) -> None:
    inspector = inspect(bind)
    if table not in inspector.get_table_names(schema=_reflect_schema(bind, schema)):
        return
    existing = {c["name"] for c in inspector.get_columns(table, schema=_reflect_schema(bind, schema))}
    with bind.begin() as conn:
        _set_lock_timeout(conn, bind)
        for column, coltype in columns.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {_q(bind, schema, table)} "
                                  f"ADD COLUMN {column} {coltype}"))


def _rebuild_sqlite_table(bind: Engine, name: str) -> None:
    """SQLite can't drop NOT NULL or UNIQUE in place: create the model's
    table under a new name, copy the rows, drop the old one, rename (SQLite's
    documented procedure; other tables' foreign keys keep the old name)."""
    tmp = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(tmp)
    new = tmp.tables[name].to_metadata(tmp, name=f"{name}__new")
    inspector = inspect(bind)
    old_columns = {c["name"] for c in inspector.get_columns(name)}
    columns = ", ".join(c.name for c in new.columns if c.name in old_columns)
    with bind.begin() as conn:
        for index in inspector.get_indexes(name):
            conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
        new.create(conn)
        conn.execute(text(f"INSERT INTO {name}__new ({columns}) SELECT {columns} FROM {name}"))
        conn.execute(text(f"DROP TABLE {name}"))
        conn.execute(text(f"ALTER TABLE {name}__new RENAME TO {name}"))


def _unowned_counts(conn, bind: Engine, schema: str) -> dict[str, int]:
    return {table: conn.execute(text(f"SELECT COUNT(*) FROM {_q(bind, schema, table)} "
                                     "WHERE owner_id IS NULL")).scalar_one()
            for table in _OWNED_TABLES}


def _backfill_owners(bind: Engine, schema: str, owner: str | None) -> None:
    """Rows from before multi-user belong to the backfill owner (the admin).

    On Postgres, rows the old app made with login off carry the local user
    ("auth-disabled", e.g. a Character Studio character, or rows copied from
    a local SQLite): they match no account, so a named backfill owner takes
    them too. Without one they stay (a Postgres used for local development)."""
    with bind.begin() as conn:
        _set_lock_timeout(conn, bind)
        counts = _unowned_counts(conn, bind, schema)
        missing = sum(counts.values())
        if missing and owner is None:
            raise owners.BackfillOwnerMissing(
                f"{missing} rows have no owner ({counts}): set BACKFILL_OWNER_EMAIL")
        if owner is None:
            return
        local = _postgres(bind) and owner != owners.LOCAL_OWNER_ID
        for table in _OWNED_TABLES:
            conn.execute(text(f"UPDATE {_q(bind, schema, table)} SET owner_id = :owner "
                              "WHERE owner_id IS NULL"
                              + (" OR owner_id = :local" if local else "")),
                         {"owner": owner, "local": owners.LOCAL_OWNER_ID})


def _backfill_scene_asset_versions(bind: Engine, schema: str) -> None:
    """Turn every pre-versioning backdrop into v1 and pin legacy posts.

    Owner-aware: a backdrop's versions and the posts pinned to it share its
    owner, since two owners may each have an `office`. Runs after
    _backfill_owners. Core statements select only columns guaranteed to
    exist, which keeps the lightweight old-schema migration tests valid as
    well as production.
    """
    from .models import Post, SceneAsset, SceneAssetVersion

    assets = SceneAsset.__table__
    versions = SceneAssetVersion.__table__
    posts = Post.__table__
    post_table = _q(bind, schema, "posts")
    with bind.begin() as conn:
        rows = conn.execute(select(
            assets.c.owner_id, assets.c.name, assets.c.detail_text, assets.c.current_version,
        )).mappings().all()
        version_ids: dict[tuple[str, str], str] = {}
        for row in rows:
            existing = conn.execute(select(versions.c.id).where(
                versions.c.owner_id == row["owner_id"],
                versions.c.scene_asset_name == row["name"],
                versions.c.version == row["current_version"],
            )).scalar_one_or_none()
            version_id = existing or str(uuid.uuid4())
            if existing is None:
                conn.execute(versions.insert().values(
                    id=version_id,
                    owner_id=row["owner_id"],
                    scene_asset_name=row["name"],
                    version=row["current_version"],
                    detail_text=row["detail_text"],
                ))
            version_ids[(row["owner_id"], row["name"])] = version_id

        legacy_posts = conn.execute(select(
            posts.c.id, posts.c.owner_id, posts.c.scene_asset_name,
        ).where(
            posts.c.scene_asset_name.is_not(None),
            posts.c.scene_asset_version_id.is_(None),
        )).mappings().all()
        for post in legacy_posts:
            version_id = version_ids.get((post["owner_id"], post["scene_asset_name"]))
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


def _relax_post_character_id(bind: Engine, schema: str) -> None:
    """posts.character_id becomes optional (a post may have no mascot yet)."""
    column = next(c for c in inspect(bind).get_columns(
        "posts", schema=_reflect_schema(bind, schema)) if c["name"] == "character_id")
    if column["nullable"]:
        return
    if _postgres(bind):
        with bind.begin() as conn:
            _set_lock_timeout(conn, bind)
            conn.execute(text(f"ALTER TABLE {_q(bind, schema, 'posts')} "
                              "ALTER COLUMN character_id DROP NOT NULL"))
    else:
        _rebuild_sqlite_table(bind, "posts")


# How long a migration DDL statement waits for a table lock before giving up
# (the old app may still be serving; a waiting ALTER would stall its queries).
_LOCK_TIMEOUT = "15s"


# table -> (old unique columns, new constraint name, new unique columns)
_OWNER_UNIQUES = {
    "scene_assets": (["name"], "uq_scene_asset_owner_name", ["owner_id", "name"]),
    "scene_asset_versions": (["scene_asset_name", "version"], "uq_scene_asset_version_owner",
                             ["owner_id", "scene_asset_name", "version"]),
}


def _owner_scoped_uniques(bind: Engine, schema: str) -> None:
    """Backdrop names are unique per owner, not globally."""
    for table, (old_cols, new_name, new_cols) in _OWNER_UNIQUES.items():
        uniques = inspect(bind).get_unique_constraints(
            table, schema=_reflect_schema(bind, schema))
        stale = [u for u in uniques if u["column_names"] == old_cols]
        has_new = any(u["column_names"] == new_cols for u in uniques)
        if not _postgres(bind):
            if stale or not has_new:
                _rebuild_sqlite_table(bind, table)
            continue
        with bind.begin() as conn:
            _set_lock_timeout(conn, bind)
            # Add the new constraint before dropping the old one, so the
            # table is never without a uniqueness rule.
            if not has_new:
                conn.execute(text(f"ALTER TABLE {_q(bind, schema, table)} ADD CONSTRAINT "
                                  f"{new_name} UNIQUE ({', '.join(new_cols)})"))
            for constraint in stale:
                conn.execute(text(f"ALTER TABLE {_q(bind, schema, table)} "
                                  f'DROP CONSTRAINT "{constraint["name"]}"'))


def _require_owner_not_null(bind: Engine, schema: str, owner: str | None) -> None:
    """Postgres: every row must have an owner from now on.

    The old app may still be serving while this runs (rollout: migrate, then
    deploy). Each table is locked against writes, rows it inserted since the
    backfill get the backfill owner, then NOT NULL is set -- all in one
    transaction, so no unowned row can slip in between.
    """
    if not _postgres(bind):
        return
    with bind.begin() as conn:
        _set_lock_timeout(conn, bind)
        pending = [table for table in _OWNED_TABLES
                   if next(c for c in inspect(conn).get_columns(table, schema=schema)
                           if c["name"] == "owner_id")["nullable"]]
        if not pending:
            return
        # All tables in one statement: locking them one by one could deadlock
        # with the old app's scene step (writes backdrops, then the post).
        conn.execute(text("LOCK TABLE " + ", ".join(_q(bind, schema, t) for t in pending)
                          + " IN SHARE ROW EXCLUSIVE MODE"))
        for table in pending:
            q = _q(bind, schema, table)
            if owner is not None:
                conn.execute(text(f"UPDATE {q} SET owner_id = :owner WHERE owner_id IS NULL"),
                             {"owner": owner})
            conn.execute(text(f"ALTER TABLE {q} ALTER COLUMN owner_id SET NOT NULL"))


def _create_owner_indexes(bind: Engine, schema: str) -> None:
    columns = {c["name"] for c in inspect(bind).get_columns(
        "posts", schema=_reflect_schema(bind, schema))}
    if not {"owner_id", "created_at"} <= columns:
        return  # only in hand-made test tables; real ones always have created_at
    with bind.begin() as conn:
        _set_lock_timeout(conn, bind)
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_owner_created ON "
                          f"{_q(bind, schema, 'posts')} (owner_id, created_at)"))


def _backfill_writer_profile(bind: Engine, owner: str | None) -> None:
    """The backfill owner keeps today's profile (content_config/user_profile.md)."""
    from ..agents.content_sources import load_user_profile
    from .models import WriterProfile

    template = load_user_profile()
    if owner is None or not template.strip():
        return
    profiles = WriterProfile.__table__
    with bind.begin() as conn:
        exists = conn.execute(select(profiles.c.owner_id).where(
            profiles.c.owner_id == owner)).first()
        if exists is None:
            conn.execute(profiles.insert().values(
                owner_id=owner, profile_md=template, updated_at=datetime.utcnow()))


def init_db(bind: Engine = engine, schema: str = settings.db_schema,
            backfill_owner_email: str | None = None) -> None:
    """Create/upgrade the schema (idempotent). Rows from before multi-user
    get the owner named by backfill_owner_email (default
    settings.backfill_owner_email); on SQLite that is always the local user."""
    from . import models  # noqa: F401 — ensures models are registered
    if _postgres(bind):
        with bind.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=bind)
    for table, columns in _COLUMNS_BY_TABLE.items():
        _add_missing_columns(bind, schema, table, columns)
    if backfill_owner_email is None:
        backfill_owner_email = settings.backfill_owner_email
    owner = owners.resolve_owner_id(bind, backfill_owner_email)
    _backfill_owners(bind, schema, owner)
    _backfill_scene_asset_versions(bind, schema)
    _backfill_scene_asset_display_names(bind)
    _relax_post_character_id(bind, schema)
    _owner_scoped_uniques(bind, schema)
    _require_owner_not_null(bind, schema, owner)
    _create_owner_indexes(bind, schema)
    _backfill_writer_profile(bind, owner)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
