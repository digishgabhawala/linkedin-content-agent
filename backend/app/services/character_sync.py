"""Copy a character-forge-v2 mascot into this app's database and Storage.

Runs on the laptop (scripts/sync_character.py), which has the forge
workspace and the Supabase service key. The hosted backend only reads the
resulting `characters` row, so it never needs upload rights. Storage is
called over plain HTTP, the same no-SDK convention as task-queue's storage.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from ..db.models import Character


class SyncError(Exception):
    pass


def sync_character(db: Session, http: httpx.Client, supabase_url: str, service_key: str,
                   bucket: str, forge_path: Path, character_id: str) -> Character:
    folder = Path(forge_path) / "workspace" / character_id
    card_path, hero_path = folder / "character.json", folder / "hero.png"
    for path in (card_path, hero_path):
        if not path.is_file():
            raise SyncError(f"missing {path}")
    card = json.loads(card_path.read_text())
    auth = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
    base = supabase_url.rstrip("/")

    # Public bucket: the browser loads the hero image straight from Storage.
    resp = http.post(f"{base}/storage/v1/bucket", headers=auth,
                     json={"id": bucket, "name": bucket, "public": True})
    exists = resp.status_code in (400, 409) and "exist" in resp.text.lower()
    if resp.status_code != 200 and not exists:
        raise SyncError(f"creating bucket {bucket!r} failed: {resp.status_code} {resp.text}")

    object_path = f"characters/{character_id}/hero.png"
    resp = http.post(f"{base}/storage/v1/object/{bucket}/{object_path}",
                     headers={**auth, "Content-Type": "image/png", "x-upsert": "true"},
                     content=hero_path.read_bytes())
    if resp.status_code != 200:
        raise SyncError(f"uploading hero.png failed: {resp.status_code} {resp.text}")

    # The row is written only after the upload succeeded. ?v= makes browsers
    # fetch a re-synced hero instead of a cached old one.
    now = datetime.now(timezone.utc)
    row = db.get(Character, character_id) or Character(character_id=character_id)
    row.display_name = card.get("display_name")
    row.personality = card.get("personality")
    row.hero_image_url = (f"{base}/storage/v1/object/public/{bucket}/{object_path}"
                          f"?v={int(now.timestamp())}")
    row.updated_at = now.replace(tzinfo=None)  # naive UTC, like every DB column
    db.add(row)
    db.commit()
    return row
