"""Copy a character-forge-v2 mascot into this app's database and Storage.

Usage (from backend/, on the machine that has character-forge-v2):
    SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_KEY=<service key> \\
        .venv/bin/python scripts/sync_character.py gtee_dev --owner-email admin@example.com \\
        [--forge-path ../../character-forge-v2] [--bucket linkedin]

Uploads workspace/<id>/hero.png to characters/<owner id>/<id>/hero.png in the
public Storage bucket (default STORAGE_BUCKET or "linkedin"; the owner is the
platform account of --owner-email) and creates or updates the `characters` row in
DATABASE_URL / DB_SCHEMA from .env. Run again whenever the mascot changes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.db.database import SessionLocal, engine, init_db
from app.db.owners import OwnerNotFound, resolve_owner_id
from app.services.character_sync import SyncError, sync_character

_DEFAULT_FORGE = Path(__file__).resolve().parents[3] / "character-forge-v2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("character_id")
    parser.add_argument("--owner-email", required=True,
                        help="platform account (email) that owns this character")
    parser.add_argument("--forge-path", type=Path, default=_DEFAULT_FORGE)
    parser.add_argument("--bucket", default=os.environ.get("STORAGE_BUCKET", "linkedin"))
    args = parser.parse_args()
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        parser.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in the environment")

    try:
        owner_id = resolve_owner_id(engine, args.owner_email)
    except OwnerNotFound as e:
        parser.error(str(e))
    init_db()
    db = SessionLocal()
    try:
        with httpx.Client(timeout=60) as http:
            row = sync_character(db, http, url, key, args.bucket, args.forge_path,
                                 args.character_id, owner_id=owner_id)
        print(f"{row.character_id}: {row.display_name!r}, hero {row.hero_image_url}")
    except SyncError as e:
        print(f"sync failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
