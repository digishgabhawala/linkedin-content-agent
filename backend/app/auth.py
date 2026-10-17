"""Login for the LinkedIn API: a Supabase session whose platform profile is
approved and has a `linkedin` membership.

Same approach as task-queue's admin page: the browser signs in with
Supabase, sends its access token, and we ask Supabase who it belongs to.
Verified tokens are cached briefly because the UI polls post status every
few seconds -- never past the token's own expiry. The approval status and
membership (platform.profiles / platform.app_memberships, owned by the parent
site) are cached for at most ACCESS_CACHE_SECONDS, so an approval or a
suspension takes effect within a minute.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from .config import settings
from .db import database
from .errors import ReasonedHTTPException

_bearer = HTTPBearer(auto_error=False)
LOCAL_USER_ID = "auth-disabled"  # the fixed local user (AUTH_ENABLED=false)
APP = "linkedin"
_MESSAGES = {"pending": "Your account is waiting for approval.",
             "rejected": "Your account was not approved.",
             "suspended": "Your account is suspended.",
             "no_membership": "Your account does not have access to LinkedIn Content Agent."}


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    # The caller's Supabase session token: lets the backend act as this user
    # where Supabase policies allow it (e.g. Storage uploads), instead of
    # holding a service key. None when login is disabled.
    access_token: str | None = None


# sha256(token) -> (user, expiry as epoch seconds)
_cache: dict[str, tuple[AuthUser, float]] = {}


@dataclass(frozen=True)
class Access:
    status: str | None  # None: no platform profile yet
    member: bool

    @property
    def refusal(self) -> str | None:
        if self.status in (None, "pending"):
            return "pending"
        if self.status != "approved":
            return self.status
        return None if self.member else "no_membership"


# user id -> (access, expiry as epoch seconds)
_access_cache: dict[str, tuple[Access, float]] = {}
_ACCESS_SQL = text(
    "select p.status, exists (select 1 from platform.app_memberships m "
    "where m.user_id = p.user_id and m.app = :app) as member "
    "from platform.profiles p where p.user_id = cast(:uid as uuid)")


def clear_cache() -> None:
    _cache.clear()
    _access_cache.clear()


def _now() -> float:
    return time.time()


def _load_access(user_id: str) -> Access:
    if database.engine.dialect.name != "postgresql":
        raise HTTPException(503, "Account checks need the platform database (Postgres)")
    try:
        uuid.UUID(user_id)
    except ValueError:
        return Access(None, False)
    with database.engine.connect() as conn:
        row = conn.execute(_ACCESS_SQL, {"uid": user_id, "app": APP}).first()
    return Access(row.status, bool(row.member)) if row else Access(None, False)


async def _access_for(user_id: str) -> Access:
    now = _now()
    cached = _access_cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]
    access = await asyncio.to_thread(_load_access, user_id)
    _access_cache[user_id] = (access, now + settings.access_cache_seconds)
    return access


def public_auth_config() -> dict:
    """Only values that are explicitly safe to expose to a browser."""
    on = settings.auth_enabled
    return {"enabled": on,
            "supabase_url": settings.supabase_url if on else None,
            "supabase_publishable_key": settings.supabase_publishable_key if on else None}


def _unauthorized() -> HTTPException:
    return HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})


async def _fetch_supabase_user(token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                                    headers={"apikey": settings.supabase_publishable_key,
                                             "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Identity service is temporarily unavailable") from exc
    if resp.status_code != 200:
        raise _unauthorized()
    return resp.json()


def _token_expiry(token: str) -> float:
    """The JWT's `exp`, read without verifying (Supabase already did that).
    0 when unreadable, so such a token is never cached."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"])
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if not settings.auth_enabled:
        return AuthUser(id=LOCAL_USER_ID, email="local@localhost")
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    key = hashlib.sha256(token.encode()).hexdigest()
    now = _now()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        user = cached[0]
    else:
        payload = await _fetch_supabase_user(token)
        user = AuthUser(id=str(payload.get("id") or ""),
                        email=str(payload.get("email") or "").strip().casefold(),
                        access_token=token)
        _cache[key] = (user, min(now + settings.auth_cache_minutes * 60, _token_expiry(token)))

    reason = (await _access_for(user.id)).refusal
    if reason:
        raise ReasonedHTTPException(403, _MESSAGES[reason], reason)
    return user
