"""Login for the LinkedIn API: a Supabase session on the allow list.

Same approach as task-queue's admin page: the browser signs in with
Supabase, sends its access token, and we ask Supabase who it belongs to.
Verified tokens are cached briefly because the UI polls post status every
few seconds -- never past the token's own expiry.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

_bearer = HTTPBearer(auto_error=False)
_LOCAL_USER_ID = "auth-disabled"


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


def clear_cache() -> None:
    _cache.clear()


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
        return AuthUser(id=_LOCAL_USER_ID, email="local@localhost")
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]

    payload = await _fetch_supabase_user(token)
    user = AuthUser(id=str(payload.get("id") or ""),
                    email=str(payload.get("email") or "").strip().casefold(),
                    access_token=token)
    if user.email not in settings.allowed_emails:
        raise HTTPException(403, "This account does not have access to LinkedIn Content Agent")
    _cache[key] = (user, min(now + settings.auth_cache_minutes * 60, _token_expiry(token)))
    return user
