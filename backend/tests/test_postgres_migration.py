"""The multi-user migration on a real Postgres with pre-multi-user data.

Opt-in: skipped unless LINKEDIN_PG_TEST_URL points at a LOCAL database (the
local Supabase that task-queue starts, with ai-bharatiya-web's platform
migration applied). Never point it at a hosted database:

    LINKEDIN_PG_TEST_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres \\
        .venv/bin/pytest -q tests/test_postgres_migration.py
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.database import build_engine, init_db
from app.db.owners import BackfillOwnerMissing

_URL = os.environ.get("LINKEDIN_PG_TEST_URL")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SCHEMA = "linkedin_migtest"
EMAIL = "migtest@platform-test.local"
OLD_SCHEMA = Path(__file__).parent / "fixtures" / "pre_multi_user_schema.sql"
OWNED = ("posts", "scene_assets", "scene_asset_versions", "characters")

pytestmark = pytest.mark.skipif(not _URL, reason="LINKEDIN_PG_TEST_URL not set (opt-in)")


@pytest.fixture()
def pg():
    url = make_url(_URL)
    if url.host not in _LOCAL_HOSTS:
        pytest.fail(f"refusing to run migration tests against non-local host {url.host!r}")
    admin = create_engine(url)
    uid = str(uuid.uuid4())
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        conn.execute(text("DELETE FROM auth.users WHERE email = :e"), {"e": EMAIL})
        conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
        conn.execute(text(f'SET LOCAL search_path TO "{SCHEMA}"'))
        conn.exec_driver_sql(OLD_SCHEMA.read_text())
        _old_rows(conn)
        conn.execute(text("INSERT INTO auth.users (id, email) VALUES (:id, :e)"),
                     {"id": uid, "e": EMAIL})  # the trigger creates its pending profile
    try:
        yield admin, uid
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            conn.execute(text("DELETE FROM auth.users WHERE email = :e"), {"e": EMAIL})
        admin.dispose()


def _old_rows(conn) -> None:
    """Rows as the pre-multi-user app wrote them (no owners anywhere)."""
    conn.execute(text(
        "INSERT INTO characters (character_id, display_name, hero_version, hero_image_url, "
        "updated_at) VALUES ('gtee_dev', 'Gtee', 3, 'https://x/characters/gtee_dev/hero.png', now())"))
    conn.execute(text(
        "INSERT INTO hero_generation_runs VALUES ('run1', 'gtee_dev', '{}', 'full', 7, 1, "
        "'completed', now(), now())"))
    conn.execute(text(
        "INSERT INTO hero_candidates (id, run_id, task_id, seed, status, image_url, created_at, "
        "updated_at) VALUES ('cand1', 'run1', 't1', 7, 'ready', "
        "'https://x/characters/gtee_dev/candidates/cand1.png', now(), now())"))
    conn.execute(text(
        "INSERT INTO scene_assets (id, name, display_name, detail_text, current_version, "
        "created_at, updated_at) VALUES ('a1', 'office', 'Office', 'office v2', 2, now(), now())"))
    conn.execute(text(
        "INSERT INTO scene_asset_versions VALUES ('v1', 'office', 1, 'office v1', now()), "
        "('v2', 'office', 2, 'office v2', now())"))
    for pid, pinned in (("p1", "'v1'"), ("p2", "NULL")):
        conn.execute(text(
            "INSERT INTO posts (id, character_id, brief, status, draft_version, "
            "recalibration_count, scene_asset_name, scene_asset_version_id, created_at, "
            f"final_image_path) VALUES ('{pid}', 'gtee_dev', 'b', 'ready', 1, 0, 'office', "
            f"{pinned}, now(), 'https://x/img/{pid}.png')"))
        conn.execute(text(
            f"INSERT INTO post_drafts VALUES ('d-{pid}', '{pid}', 1, 'text {pid}', 'draft', "
            "NULL, now())"))
        conn.execute(text(
            f"INSERT INTO feedback VALUES ('f-{pid}', '{pid}', 'draft', NULL, 'note', now())"))


def _q(conn, sql: str, **params):
    return conn.execute(text(sql), params)


def _constraints(conn) -> set[str]:
    return set(_q(conn, "SELECT c.conname FROM pg_constraint c JOIN pg_namespace n "
                        "ON n.oid = c.connamespace WHERE n.nspname = :s", s=SCHEMA).scalars())


def test_migration_backfills_owners_swaps_constraints_and_keeps_data(pg):
    admin, uid = pg
    engine = build_engine(_URL, SCHEMA)
    init_db(engine, SCHEMA, backfill_owner_email=EMAIL.upper())

    with admin.connect() as conn:
        _q(conn, f'SET search_path TO "{SCHEMA}"')
        for table in OWNED:
            owners = _q(conn, f"SELECT DISTINCT owner_id FROM {table}").scalars().all()
            assert owners == [uid], table
        nullable = dict(_q(conn, "SELECT table_name || '.' || column_name, is_nullable FROM "
                                 "information_schema.columns WHERE table_schema = :s AND "
                                 "column_name IN ('owner_id', 'character_id')", s=SCHEMA).all())
        assert all(nullable[f"{t}.owner_id"] == "NO" for t in OWNED), nullable
        assert nullable["posts.character_id"] == "YES"
        constraints = _constraints(conn)
        assert {"uq_scene_asset_owner_name", "uq_scene_asset_version_owner"} <= constraints
        assert not {"scene_assets_name_key", "uq_scene_asset_version"} & constraints
        # data intact: posts, drafts, feedback, pinned + newly pinned backdrops, hero history
        assert _q(conn, "SELECT id, scene_asset_version_id, final_image_path FROM posts "
                        "ORDER BY id").all() == [("p1", "v1", "https://x/img/p1.png"),
                                                 ("p2", "v2", "https://x/img/p2.png")]
        assert _q(conn, "SELECT count(*) FROM post_drafts d JOIN posts p ON p.id = d.post_id"
                  ).scalar_one() == 2
        assert _q(conn, "SELECT count(*) FROM feedback").scalar_one() == 2
        assert _q(conn, "SELECT count(*) FROM scene_asset_versions").scalar_one() == 2
        assert _q(conn, "SELECT image_url FROM hero_candidates").scalar_one().endswith("cand1.png")
        assert _q(conn, "SELECT hero_image_url FROM characters").scalar_one().endswith("hero.png")
        assert _q(conn, "SELECT owner_id FROM writer_profiles").scalars().all() == [uid]
        assert _q(conn, "SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = "
                        "'ix_posts_owner_created'", s=SCHEMA).scalar_one() == 1
        before = {t: _q(conn, f"SELECT count(*) FROM {t}").scalar_one()
                  for t in (*OWNED, "post_drafts", "feedback", "writer_profiles")}

    # Second run (no email needed now that every row has an owner): a no-op.
    init_db(engine, SCHEMA, backfill_owner_email="")
    with admin.connect() as conn:
        _q(conn, f'SET search_path TO "{SCHEMA}"')
        after = {t: _q(conn, f"SELECT count(*) FROM {t}").scalar_one() for t in before}
        assert after == before and _constraints(conn) == constraints
        # Two owners may now share a backdrop name; one owner may not repeat it.
        _q(conn, "INSERT INTO scene_assets (id, owner_id, name, detail_text, current_version) "
                 "VALUES ('b1', 'someone-else', 'office', 'x', 1)")
        conn.commit()
    engine.dispose()


def test_unowned_rows_without_a_backfill_email_stop_the_migration(pg):
    _ = pg
    engine = build_engine(_URL, SCHEMA)
    with pytest.raises(BackfillOwnerMissing):
        init_db(engine, SCHEMA, backfill_owner_email="")
    engine.dispose()
