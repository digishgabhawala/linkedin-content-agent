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
