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
    monkeypatch.setattr(settings, "auth_allowed_emails", "Admin@Example.com")
    auth.clear_cache()
    fake = {"calls": 0, "email": "admin@example.com", "error": None}

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
    assert me.json() == {"email": "admin@example.com"}


def test_other_email_is_403(api, supabase):
    supabase["email"] = "someone@else.com"
    assert _get(api, token=_token()).status_code == 403


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


def test_forbidden_users_are_not_cached(api, supabase):
    supabase["email"] = "someone@else.com"
    token = _token()
    _get(api, token=token)
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
        path = route.path.replace("{post_id}", "x").replace("{name}", "x")
        for method in route.methods:
            resp = api.request(method, path)
            assert resp.status_code == 401, f"{method} {route.path} answered {resp.status_code}"
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("missing", ["supabase_url", "supabase_publishable_key",
                                     "auth_allowed_emails"])
def test_enabled_auth_requires_its_settings(missing):
    values = {"auth_enabled": True, "supabase_url": "https://p.supabase.co",
              "supabase_publishable_key": "pk", "auth_allowed_emails": "a@b.c"}
    values[missing] = ""
    with pytest.raises(ValidationError, match=missing.upper()):
        Settings(_env_file=None, **values)
