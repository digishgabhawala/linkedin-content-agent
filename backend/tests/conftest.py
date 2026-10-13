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
