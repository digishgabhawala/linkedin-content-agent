import os

# Tests must never touch a real database: backend/.env may point
# DATABASE_URL at the hosted Supabase project. Force an in-memory SQLite DB
# before the app's settings/engine are imported (env beats .env).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Login is opt-in per test (test_auth.py); a developer's .env may enable it.
os.environ["AUTH_ENABLED"] = "false"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import (
    models,  # noqa: F401 -- registers Post/PostDraft/SceneAsset/Feedback on Base
)
from app.db.database import Base, engine

assert engine.url.get_backend_name() == "sqlite", "tests must not use a real database"


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite DB per test -- independent of the real
    app.db.database.engine (which is bound to settings.db_path, a real file)."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def api():
    """TestClient on a fresh in-memory DB with a FakeQueue for task-queue calls."""
    from fastapi.testclient import TestClient

    from app.api import routes
    from app.db.database import get_db
    from app.main import app
    from tests.test_steps import FakeQueue

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    tc = TestClient(app)  # no `with`: lifespan (real init_db) is not run
    tc.queue = FakeQueue()  # tests may swap it (e.g. for a DownQueue)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    async def client():
        yield tc.queue

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[routes.get_http_client] = client
    app.dependency_overrides[routes.get_llm_client] = client
    tc.session_factory = Session
    yield tc
    app.dependency_overrides.clear()


@pytest.fixture()
def users(api):
    """switch(user_id) signs the test client in as that user (auth checks
    bypassed): both the router-level dependency and route parameters see it."""
    from app.auth import AuthUser, current_user
    from app.main import app
    state = {"user": AuthUser(id="user-a", email="user-a@example.com")}
    app.dependency_overrides[current_user] = lambda: state["user"]

    def switch(user_id: str) -> AuthUser:
        state["user"] = AuthUser(id=user_id, email=f"{user_id}@example.com")
        return state["user"]
    return switch
