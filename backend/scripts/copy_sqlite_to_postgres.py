"""Copy this app's data from one database to another (one-off).

Usage (from backend/):
    .venv/bin/python scripts/copy_sqlite_to_postgres.py \\
        --source sqlite:///posts.db --target "$DATABASE_URL" [--schema linkedin]

--target defaults to DATABASE_URL and --schema to DB_SCHEMA from .env.
Refuses to run if the target already has rows. The source is left as is.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.copy import TargetNotEmpty, copy_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=f"sqlite:///{settings.db_path}")
    parser.add_argument("--target", default=settings.database_url)
    parser.add_argument("--schema", default=settings.db_schema)
    args = parser.parse_args()
    if not args.target:
        parser.error("--target (or DATABASE_URL) is required")
    try:
        counts = copy_database(args.source, args.target, args.schema)
    except TargetNotEmpty as e:
        print(f"refusing to copy: {e}", file=sys.stderr)
        return 1
    for table, n in counts.items():
        print(f"{table}: {n} rows copied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
