"""Supabase Storage policies this app needs (Postgres/Supabase only).

Hero candidates are copied into Storage with the signed-in user's own
session, so the hosted app never holds the service key. These policies let
an authenticated user write -- and nothing else -- under
``<bucket>/characters/``. Sign-ups are disabled on the shared project, so
only accounts the admin created can ever hold such a session. Applied by
scripts/init_db.py; idempotent (drop + create).
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.engine import Engine

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_PREFIX = "characters"


def policy_statements(bucket: str) -> list[str]:
    if not _BUCKET.fullmatch(bucket):
        raise ValueError(f"unsafe Storage bucket name: {bucket!r}")
    scope = f"bucket_id = '{bucket}' and (storage.foldername(name))[1] = '{_PREFIX}'"
    statements = []
    # Upsert (x-upsert) needs select + insert + update on the object row.
    for action, clause in (("select", f"using ({scope})"),
                           ("insert", f"with check ({scope})"),
                           ("update", f"using ({scope}) with check ({scope})")):
        policy = f"{bucket}_{_PREFIX}_authenticated_{action}"
        statements.append(f'drop policy if exists "{policy}" on storage.objects')
        statements.append(
            f'create policy "{policy}" on storage.objects for {action} '
            f"to authenticated {clause}")
    return statements


def apply_storage_policies(bind: Engine, bucket: str) -> bool:
    """Returns False (no-op) when the database is not Postgres."""
    if bind.dialect.name != "postgresql":
        return False
    with bind.begin() as conn:
        for statement in policy_statements(bucket):
            conn.execute(text(statement))
    return True
