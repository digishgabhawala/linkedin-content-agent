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
    from app.auth import LOCAL_USER_ID
    from app.db.models import WriterProfile
    with Session() as s:  # the local user has a profile and a mascot (onboarding done)
        s.add(WriterProfile(owner_id=LOCAL_USER_ID, profile_md="I build things."))
        s.add(_mascot(LOCAL_USER_ID))
        s.commit()
    yield tc
    app.dependency_overrides.clear()


def _mascot(owner_id: str):
    """A locked-hero character, old enough that a test's own characters are
    newer (and so the default)."""
    from datetime import datetime, timedelta

    from app.db.models import Character
    return Character(character_id=f"{owner_id}-mascot", owner_id=owner_id,
                     hero_image_url="https://h/mascot.png",
                     updated_at=datetime.utcnow() - timedelta(days=365))


@pytest.fixture()
def users(api):
    """switch(user_id) signs the test client in as that user (auth checks
    bypassed): both the router-level dependency and route parameters see it."""
    from app.auth import AuthUser, current_user
    from app.main import app
    state = {"user": AuthUser(id="user-a", email="user-a@example.com")}
    app.dependency_overrides[current_user] = lambda: state["user"]

    def switch(user_id: str, with_profile: bool = True,
               with_character: bool | None = None) -> AuthUser:
        """with_character defaults to with_profile: a user who finished
        onboarding has a profile and a mascot."""
        from app.db.models import Character, WriterProfile
        if with_character is None:
            with_character = with_profile
        state["user"] = AuthUser(id=user_id, email=f"{user_id}@example.com")
        with api.session_factory() as s:
            if with_profile and s.get(WriterProfile, user_id) is None:
                s.add(WriterProfile(owner_id=user_id, profile_md="I build things."))
            if with_character and s.get(Character, f"{user_id}-mascot") is None:
                s.add(_mascot(user_id))
            s.commit()
        return state["user"]
    return switch
