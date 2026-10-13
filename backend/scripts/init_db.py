"""Create or upgrade this app's schema, tables and columns (idempotent).

Usage (from backend/):
    .venv/bin/python scripts/init_db.py

Uses DATABASE_URL / DB_SCHEMA from .env. The hosted app runs with
AUTO_INIT_DB=false, so run this against production before deploying a
change that adds tables or columns.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.database import engine, init_db


def main() -> int:
    init_db()
    print(f"schema {settings.db_schema!r} is up to date on {engine.url.render_as_string()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
