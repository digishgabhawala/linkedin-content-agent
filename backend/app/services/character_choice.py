"""Which of the owner's characters a post uses (spec B4)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Character


class CharacterNotOwned(LookupError):
    """The character doesn't exist or belongs to someone else (shown as 404)."""


class MascotRequired(LookupError):
    """No usable mascot: the owner has no character with a locked hero, or
    the requested one has none yet (shown as 409 character_required)."""


def choose_character(db: Session, *, owner_id: str, requested: str | None) -> str:
    """A post needs a mascot. A requested id must be the owner's and have a
    locked hero. Without one: the owner's most recently updated character
    with a locked hero."""
    if requested:
        character = db.get(Character, requested)
        if character is None or character.owner_id != owner_id:
            raise CharacterNotOwned(f"character {requested!r} not found")
        if not character.hero_image_url:
            raise MascotRequired(f"character {requested!r} has no locked hero yet")
        return character.character_id
    chosen = db.scalars(
        select(Character.character_id)
        .where(Character.owner_id == owner_id, Character.hero_image_url.is_not(None),
               Character.hero_image_url != "")
        .order_by(Character.updated_at.desc())
        .limit(1)).first()
    if chosen is None:
        raise MascotRequired("Create your mascot first: a character with a locked hero")
    return chosen
