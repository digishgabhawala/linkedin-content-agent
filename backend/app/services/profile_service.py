"""The writer profile (who the writer is): one Markdown record per user.

content_config/user_profile.md is only the template offered to new users
(and the backfill for the pre-multi-user owner)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..agents.content_sources import load_user_profile
from ..db.models import WriterProfile

MAX_PROFILE_CHARS = 8000


def template() -> str:
    return load_user_profile()


def get_profile(db: Session, owner_id: str) -> WriterProfile | None:
    return db.get(WriterProfile, owner_id)


def profile_text(db: Session, owner_id: str) -> str:
    profile = get_profile(db, owner_id)
    return profile.profile_md if profile else ""


def save_profile(db: Session, owner_id: str, profile_md: str) -> WriterProfile:
    profile = get_profile(db, owner_id)
    if profile is None:
        profile = WriterProfile(owner_id=owner_id)
        db.add(profile)
    profile.profile_md = profile_md
    profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return profile
