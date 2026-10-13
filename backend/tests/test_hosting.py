"""Hosting: no dependence on the working folder; no table setup on every start."""
import asyncio

from app import main
from app.agents.content_sources import load_skill, load_user_profile
from app.config import settings


def test_content_config_loads_from_any_working_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_user_profile().strip()
    assert load_skill().strip()


def _run_lifespan():
    async def go():
        async with main.lifespan(main.app):
            pass
    asyncio.run(go())


def test_startup_skips_table_setup_when_auto_init_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append(1))
    monkeypatch.setattr(settings, "auto_init_db", False)
    _run_lifespan()
    assert calls == []
    monkeypatch.setattr(settings, "auto_init_db", True)
    _run_lifespan()
    assert calls == [1]


def _site(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("js")
    web = FastAPI()
    web.include_router(main.public_router)
    main.mount_frontend(web, tmp_path)
    return TestClient(web, follow_redirects=False)


def test_frontend_is_served_under_linkedin(tmp_path):
    client = _site(tmp_path)
    # Both spellings serve the app: the parent site strips trailing slashes
    # (/linkedin/ -> /linkedin), so redirecting /linkedin -> /linkedin/
    # would loop.
    assert client.get("/linkedin").text == "<html>app</html>"
    assert client.get("/linkedin/").text == "<html>app</html>"
    assert client.get("/linkedin/assets/app.js").text == "js"
    assert client.get("/api/linkedin/health").json() == {"status": "ok"}


def test_deep_links_fall_back_to_the_app(tmp_path):
    client = _site(tmp_path)
    assert client.get("/linkedin/posts/abc").text == "<html>app</html>"
    assert client.get("/linkedin/assets/missing.js").status_code == 404


def test_root_redirect_stays_on_the_callers_host(tmp_path):
    # Behind the parent site's rewrite, an absolute redirect would send the
    # browser to this deployment's own hostname.
    resp = _site(tmp_path).get("/")
    assert resp.status_code in (307, 308)
    assert resp.headers["location"] == "/linkedin"


def test_old_api_paths_are_gone(api):
    assert api.get("/api/posts").status_code == 404
    assert api.get("/api/linkedin/posts").status_code == 200


def test_missing_frontend_build_is_skipped(tmp_path):
    from fastapi import FastAPI
    web = FastAPI()
    main.mount_frontend(web, tmp_path / "nope")
    assert [r.path for r in web.routes] == [r.path for r in FastAPI().routes]
