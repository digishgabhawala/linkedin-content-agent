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


def test_built_frontend_is_served_next_to_the_api(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("js")
    web = FastAPI()
    web.include_router(main.public_router)
    main.mount_frontend(web, tmp_path)
    client = TestClient(web)
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/assets/app.js").text == "js"
    assert client.get("/api/health").json() == {"status": "ok"}


def test_missing_frontend_build_is_skipped(tmp_path):
    from fastapi import FastAPI
    web = FastAPI()
    main.mount_frontend(web, tmp_path / "nope")
    assert [r.path for r in web.routes] == [r.path for r in FastAPI().routes]
