"""Find and optionally delete unreferenced Supabase Storage images.

Usage (from backend/, after sourcing task-queue's service credentials):
    .venv/bin/python scripts/sweep_storage.py [--apply] \
        [--artifacts-before YYYY-MM-DD]

The default is a dry run. The artifacts bucket is skipped unless an explicit
cutoff is supplied, protecting files from other producers such as demo-reel.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Character, HeroCandidate, Post
from app.services.storage_sweep import StoredObject, classify, discard_stale_candidates


_PAGE_SIZE = 1000
_DEMO_REEL_WARNING = (
    "WARNING: artifacts may belong to demo-reel. Use a cutoff no later than "
    "the date demo-reel began storing artifacts."
)


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _created_at(value: str | None, now: datetime) -> datetime:
    if not value:
        return now
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _list_objects(
        http: httpx.Client, base: str, key: str, bucket: str, *,
        prefix: str = "", recursive: bool = False,
        now: datetime) -> list[StoredObject]:
    objects = []
    offset = 0
    while True:
        response = http.post(
            f"{base}/storage/v1/object/list/{bucket}",
            headers=_auth(key),
            json={
                "prefix": prefix,
                "limit": _PAGE_SIZE,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError(f"unexpected Storage listing for {bucket}/{prefix}")
        for row in rows:
            name = row.get("name")
            if not name:
                continue
            path = f"{prefix.rstrip('/')}/{name}".lstrip("/")
            metadata = row.get("metadata")
            if metadata is None:
                if recursive:
                    objects.extend(_list_objects(
                        http, base, key, bucket, prefix=path,
                        recursive=True, now=now,
                    ))
                continue
            objects.append(StoredObject(
                bucket=bucket,
                path=path,
                size=int(metadata.get("size") or 0),
                created_at=_created_at(row.get("created_at"), now),
            ))
        if len(rows) < _PAGE_SIZE:
            break
        offset += len(rows)
    return objects


def _without_query(url: str) -> str:
    parts = urlsplit(url)
    return parts._replace(query="", fragment="").geturl()


def _storage_path(url: str | None, base: str, bucket: str) -> str | None:
    if not url:
        return None
    expected = urlsplit(base).hostname
    parts = urlsplit(url)
    prefix = f"/storage/v1/object/public/{bucket}/"
    if parts.hostname != expected or not parts.path.startswith(prefix):
        return None
    return unquote(parts.path.removeprefix(prefix))


def _keep_sets(db, base: str, bucket: str) -> tuple[set[str], set[str]]:
    urls = {
        value for value in db.scalars(select(Post.final_image_path)).all() if value
    }
    urls.update(
        value for value in db.scalars(select(Character.hero_image_url)).all() if value
    )
    candidates = db.scalars(select(HeroCandidate).where(
        HeroCandidate.status != "discarded"
    )).all()
    urls.update(candidate.image_url for candidate in candidates if candidate.image_url)
    paths = {
        candidate.storage_path for candidate in candidates if candidate.storage_path
    }
    for url in urls:
        path = _storage_path(url, base, bucket)
        if path:
            paths.add(path)
    return {_without_query(url) for url in urls}, paths


def _mb(size: int) -> str:
    return f"{size / (1024 * 1024):.2f} MB"


def _category(obj: StoredObject) -> str:
    if obj.bucket == "artifacts":
        return "artifacts"
    if "/candidates/" in obj.path:
        return "linkedin candidates"
    if obj.path.endswith("/hero.png"):
        return "linkedin old heroes"
    return "linkedin other character files"


def _print_summary(objects: list[StoredObject], deletions: list[StoredObject]) -> None:
    for bucket in ("linkedin", "artifacts"):
        rows = [obj for obj in objects if obj.bucket == bucket]
        print(f"{bucket} total: {len(rows)} files, {_mb(sum(obj.size for obj in rows))}")
    categories = defaultdict(list)
    for obj in deletions:
        categories[_category(obj)].append(obj)
    if not categories:
        print("to delete: 0 files, 0.00 MB")
        return
    for category in sorted(categories):
        rows = categories[category]
        print(f"to delete - {category}: {len(rows)} files, "
              f"{_mb(sum(obj.size for obj in rows))}")


def _delete(http: httpx.Client, base: str, key: str, obj: StoredObject) -> None:
    response = http.delete(
        f"{base}/storage/v1/object/{obj.bucket}/{obj.path}",
        headers=_auth(key),
    )
    if response.status_code not in (400, 404):
        response.raise_for_status()


def _cutoff(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="delete classified objects and persist stale candidate status")
    parser.add_argument("--artifacts-before", metavar="YYYY-MM-DD",
                        help="opt in to artifacts older than this UTC date")
    args = parser.parse_args()
    try:
        artifacts_before = _cutoff(args.artifacts_before)
    except ValueError:
        parser.error("--artifacts-before must be a valid YYYY-MM-DD date")
    if artifacts_before is not None:
        print(_DEMO_REEL_WARNING)

    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        parser.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in the environment")

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        stale_count = discard_stale_candidates(db)
        db.flush()
        keep_urls, keep_paths = _keep_sets(db, base, settings.storage_bucket)
        with httpx.Client(timeout=60) as http:
            objects = _list_objects(
                http, base, key, settings.storage_bucket,
                recursive=True, now=now,
            )
            objects.extend(_list_objects(
                http, base, key, "artifacts", recursive=True, now=now,
            ))
            deletions = classify(
                objects, keep_urls=keep_urls, keep_paths=keep_paths, now=now,
                artifacts_before=artifacts_before,
            )
            _print_summary(objects, deletions)
            print(f"stale candidate rows: {stale_count}")
            if not args.apply:
                print("dry run: pass --apply to delete these files")
                return 0
            # Candidate rows stop referring to these files before deletion.
            # A failed delete then leaves a harmless orphan for the next run.
            db.commit()
            for obj in deletions:
                _delete(http, base, key, obj)
        print(f"deleted {len(deletions)} files and committed candidate updates")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
