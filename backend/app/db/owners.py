"""Who owns rows that existed before multi-user (backfill) and local data."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

LOCAL_OWNER_ID = "auth-disabled"  # the fixed local user (AUTH_ENABLED=false)


class OwnerNotFound(RuntimeError):
    pass


class BackfillOwnerMissing(RuntimeError):
    pass


def resolve_owner_id(bind: Engine, email: str | None) -> str | None:
    """The platform user id for `email` (Postgres), or the local user (SQLite).

    None on Postgres when no email is given: the migration then refuses to run
    only if it finds rows without an owner.
    """
    if bind.dialect.name != "postgresql":
        return LOCAL_OWNER_ID
    if not email or not email.strip():
        return None
    with bind.connect() as conn:
        row = conn.execute(text("select user_id::text from platform.profiles "
                                "where lower(email) = lower(:email)"),
                           {"email": email.strip()}).first()
    if row is None:
        raise OwnerNotFound(f"no platform profile for {email!r}: apply the platform migration first")
    return row[0]
