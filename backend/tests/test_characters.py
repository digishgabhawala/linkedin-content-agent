"""Mascot data comes from the `characters` table, not the laptop's forge folder."""
import asyncio

import pytest

from app.api import routes
from app.auth import LOCAL_USER_ID
from app.db.models import Character, Post
from app.services import steps
from tests.test_steps import LONG_BRIEF, FakeQueue


def test_post_loads_its_character_or_none(db_session):
    db_session.add(Character(owner_id=LOCAL_USER_ID, character_id="gtee_dev", personality="dry humor",
                             hero_image_url="https://x/hero.png?v=1"))
    db_session.add_all([Post(owner_id=LOCAL_USER_ID, id="a", character_id="gtee_dev", brief="b"),
                        Post(owner_id=LOCAL_USER_ID, id="b", character_id="nobody", brief="b")])
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Post, "a").character.personality == "dry humor"
    assert db_session.get(Post, "b").character is None


def test_draft_prompt_carries_the_rows_personality_only_when_present(db_session):
    q = FakeQueue()
    db_session.add(Character(owner_id=LOCAL_USER_ID, character_id="gtee_dev", personality="asks 'is it webscale?'"))
    with_row = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief=LONG_BRIEF, status="clarifying",
                    category="lessons_learned", clarify_transcript="[]")
    no_row = Post(owner_id=LOCAL_USER_ID, character_id="nobody", brief=LONG_BRIEF, status="clarifying",
                  category="lessons_learned", clarify_transcript="[]")
    db_session.add_all([with_row, no_row])
    db_session.commit()
    for post in (with_row, no_row):
        asyncio.run(steps._begin(db_session, q, post, "draft", {"automatic": True, "attempt": 1}))
        system = q.latest()["payload"]["messages"][0]["content"]
        assert ("is it webscale?" in system) is (post is with_row)
        assert ("BRAND CHARACTER VOICE" in system) is (post is with_row)


@pytest.mark.parametrize("final, has_character, expected", [
    ("https://s/img.png", True, "https://s/img.png"),           # the post's own render
    (None, True, "https://x/hero.png?v=1"),                     # placeholder: the mascot
    (None, False, None),                                        # no mascot row: nothing
    ("/Users/me/generated/images/old.png", True, "https://x/hero.png?v=1"),  # legacy path
])
def test_image_url(db_session, final, has_character, expected):
    if has_character:
        db_session.add(Character(owner_id=LOCAL_USER_ID, character_id="gtee_dev", hero_image_url="https://x/hero.png?v=1"))
    db_session.add(Post(owner_id=LOCAL_USER_ID, id="p", character_id="gtee_dev", brief="b", final_image_path=final))
    db_session.commit()
    db_session.expire_all()
    assert routes._image_url(db_session.get(Post, "p")) == expected
