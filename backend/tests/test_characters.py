"""Mascot data comes from the `characters` table, not the laptop's forge folder."""
from app.db.models import Character, Post


def test_post_loads_its_character_or_none(db_session):
    db_session.add(Character(character_id="gtee_dev", personality="dry humor",
                             hero_image_url="https://x/hero.png?v=1"))
    db_session.add_all([Post(id="a", character_id="gtee_dev", brief="b"),
                        Post(id="b", character_id="nobody", brief="b")])
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Post, "a").character.personality == "dry humor"
    assert db_session.get(Post, "b").character is None
