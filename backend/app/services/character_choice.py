"""Which of the owner's characters a post uses (spec B4)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Character


class CharacterNotOwned(LookupError):
    """The character doesn't exist or belongs to someone else (shown as 404)."""


def choose_character(db: Session, *, owner_id: str, requested: str | None) -> str | None:
    """A requested id must be the owner's. Without one: the owner's most
    recently updated character with a locked hero, or None (text steps work
    without a character; the image asks for one)."""
    if requested:
        character = db.get(Character, requested)
        if character is None or character.owner_id != owner_id:
            raise CharacterNotOwned(f"character {requested!r} not found")
        return character.character_id
    return db.scalars(
        select(Character.character_id)
        .where(Character.owner_id == owner_id, Character.hero_image_url.is_not(None))
        .order_by(Character.updated_at.desc())
        .limit(1)).first()
