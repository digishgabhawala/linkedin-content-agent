"""Login: Supabase token + allow list, cached; only health/config are public."""
import base64
import json
import time

import httpx
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app import auth
from app.config import Settings, settings
from app.main import app

PUBLIC = {"/api/linkedin/health", "/api/linkedin/auth/config"}
_REAL_LOAD_ACCESS = auth._load_access  # the supabase fixture swaps it out


def _token(exp_in: float = 3600) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": time.time() + exp_in}).encode()).decode().rstrip("=")
    return f"h.{payload}.s"


@pytest.fixture()
def supabase(monkeypatch):
    """Auth on, with Supabase's /auth/v1/user replaced by a fake."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "supabase_url", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "pk")
    auth.clear_cache()
    fake = {"calls": 0, "email": "admin@example.com", "error": None,
            "access": auth.Access("approved", True), "access_calls": 0}

    def load_access(user_id):
        fake["access_calls"] += 1
        return fake["access"]

    monkeypatch.setattr(auth, "_load_access", load_access)

    async def fetch(token):
        fake["calls"] += 1
        if fake["error"]:
            raise fake["error"]
        return {"id": "u1", "email": fake["email"]}

    monkeypatch.setattr(auth, "_fetch_supabase_user", fetch)
    yield fake
    auth.clear_cache()


def _get(api, path="/api/linkedin/posts", token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return api.get(path, headers=headers)


def test_no_token_is_401_with_bearer_challenge(api, supabase):
    resp = _get(api)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_401(api, supabase):
    supabase["error"] = HTTPException(401, "Authentication required")
    assert _get(api, token=_token()).status_code == 401


def test_allowed_email_any_case_gets_in(api, supabase):
    assert _get(api, token=_token()).status_code == 200
    me = _get(api, "/api/linkedin/auth/me", token=_token())
    assert me.json() == {"email": "admin@example.com", "user_id": "u1"}


def test_supabase_unreachable_is_503(api, supabase):
    supabase["error"] = HTTPException(503, "Identity service is temporarily unavailable")
    assert _get(api, token=_token()).status_code == 503


def test_fetch_maps_network_errors_to_503(monkeypatch):
    class Down:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(auth.httpx, "AsyncClient", Down)
    with pytest.raises(HTTPException) as exc:
        import asyncio
        asyncio.run(auth._fetch_supabase_user("t"))
    assert exc.value.status_code == 503


def test_verified_token_is_cached(api, supabase):
    token = _token()
    _get(api, token=token)
    _get(api, token=token)
    assert supabase["calls"] == 1


def test_cache_never_outlives_the_token(api, supabase):
    token = _token(exp_in=1)
    _get(api, token=token)
    time.sleep(1.1)
    _get(api, token=token)
    assert supabase["calls"] == 2


def test_public_routes_need_no_token(api, supabase):
    assert _get(api, "/api/linkedin/health").status_code == 200
    config = _get(api, "/api/linkedin/auth/config").json()
    assert config == {"enabled": True, "supabase_url": "https://proj.supabase.co",
                      "supabase_publishable_key": "pk"}


def test_config_hides_values_when_disabled(api):
    assert _get(api, "/api/linkedin/auth/config").json() == {
        "enabled": False, "supabase_url": None, "supabase_publishable_key": None}


def test_every_other_route_requires_login(api, supabase):
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in PUBLIC:
            continue
        path = route.path
        for parameter in ("post_id", "name", "character_id", "run_id", "candidate_id"):
            path = path.replace(f"{{{parameter}}}", "x")
        for method in route.methods:
            resp = api.request(method, path)
            assert resp.status_code == 401, f"{method} {route.path} answered {resp.status_code}"
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("missing", ["supabase_url", "supabase_publishable_key"])
def test_enabled_auth_requires_its_settings(missing):
    values = {"auth_enabled": True, "supabase_url": "https://p.supabase.co",
              "supabase_publishable_key": "pk"}
    values[missing] = ""
    with pytest.raises(ValidationError, match=missing.upper()):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize("access,reason", [
    (auth.Access("pending", False), "pending"), (auth.Access("rejected", False), "rejected"),
    (auth.Access("suspended", True), "suspended"), (auth.Access(None, False), "pending"),
    (auth.Access("approved", False), "no_membership"),
])
def test_refused_accounts_get_403_with_a_reason(api, supabase, access, reason):
    supabase["access"] = access
    resp = _get(api, token=_token())
    assert resp.status_code == 403
    assert resp.json()["reason"] == reason and resp.json()["detail"]


def test_approved_member_gets_in(api, supabase):
    assert _get(api, token=_token()).status_code == 200


def test_access_is_rechecked_after_60_seconds(api, supabase, monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr(auth, "_now", lambda: clock[0])
    token = _token()
    assert _get(api, token=token).status_code == 200
    supabase["access"] = auth.Access("suspended", True)
    assert _get(api, token=token).status_code == 200          # within 60 s: cached
    clock[0] += 61
    resp = _get(api, token=token)
    assert resp.status_code == 403 and resp.json()["reason"] == "suspended"
    assert supabase["calls"] == 1                              # identity still cached
    assert supabase["access_calls"] == 2


def test_allow_list_is_retired():
    s = Settings(_env_file=None, auth_enabled=True, supabase_url="https://p.supabase.co",
                 supabase_publishable_key="pk")
    assert not hasattr(s, "allowed_emails")


def test_access_needs_postgres():
    with pytest.raises(HTTPException) as exc:
        auth._load_access("00000000-0000-0000-0000-000000000000")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("status,expected", [(400, 401), (401, 401), (403, 401), (429, 503), (500, 503),
                                             (503, 503)])
def test_only_a_rejected_token_is_401(monkeypatch, status, expected):
    # A Supabase blip (rate limit, outage) must not look like "signed out": the
    # UI clears the shared session and sends the user to /login on a 401.
    class Answer:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return httpx.Response(status, json={})

    monkeypatch.setattr(auth.httpx, "AsyncClient", Answer)
    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._fetch_supabase_user("t"))
    assert exc.value.status_code == expected


def test_database_error_during_access_check_is_503(api, supabase, monkeypatch):
    """A DB outage while checking approval/membership is 'unavailable' (503),
    not a crash (500) -- and never a refusal or a sign-out."""
    from sqlalchemy.exc import OperationalError

    from app.db import database

    class Dialect:
        name = "postgresql"

    class BrokenEngine:
        dialect = Dialect()

        def connect(self):
            raise OperationalError("select 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database, "engine", BrokenEngine())
    monkeypatch.setattr(auth, "_load_access", _REAL_LOAD_ACCESS)

    async def fetch(token):
        return {"id": "00000000-0000-0000-0000-0000000000a1", "email": "a@example.com"}

    monkeypatch.setattr(auth, "_fetch_supabase_user", fetch)
    resp = _get(api, token=_token())
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()

