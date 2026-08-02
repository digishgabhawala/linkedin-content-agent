"""content_sources.py -- loads the three config dimensions from
CONTENT_QUALITY_DESIGN.md: user_profile.md (WHO), skill.md (HOW), and the
character's personality (the brand mascot's POV, read directly off
character-forge-v2's character.json -- never imported, per this workspace's
"standalone, shares nothing" convention, just a plain file read).

Files are read fresh on every call rather than cached at import time -- these
are meant to be hand-edited between runs (skill.md evolves, user_profile.md
will eventually be one-of-N), and a running server shouldn't require a
restart to pick up an edit.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from ..config import settings


def load_user_profile() -> str:
    path = Path(settings.user_profile_path)
    return path.read_text() if path.exists() else ""


def load_skill() -> str:
    path = Path(settings.skill_path)
    return path.read_text() if path.exists() else ""


def _example_blocks() -> dict[str, list[str]]:
    """Parses content_config/example_posts.md into {category: [example, ...]}.
    Categories are delimited by "## CATEGORY: <name>" headers; each category
    holds several "### Example N (shape)" blocks, split out individually so
    callers can pick one rather than getting the whole category at once."""
    path = Path(settings.example_posts_path)
    if not path.exists():
        return {}
    text = path.read_text()
    blocks: dict[str, list[str]] = {}
    for chunk in text.split("## CATEGORY: ")[1:]:
        name, _, rest = chunk.partition("\n")
        category_body = rest.split("\n---", 1)[0].strip()
        examples = [e.strip() for e in category_body.split("### Example ")[1:] if e.strip()]
        blocks[name.strip()] = examples
    return blocks


def load_example_for_category(category: str) -> str | None:
    """ONE randomly-chosen example's post text (no score commentary) -- for
    draft_agent's style reference. Only the matching category, and only one
    of its five, deliberately -- the random rotation is itself the point
    (see example_posts.md's own docstring for why: a single fixed example
    is what caused the 2026-07-18 over-anchoring bug)."""
    examples = _example_blocks().get(category)
    if not examples:
        return None
    chosen = random.choice(examples)
    _, _, body = chosen.partition("\n\n")  # drop the "N (shape)" label line
    return body.split("*Score emphasis:*")[0].strip()


def load_all_examples(limit_per_category: int = 2) -> str:
    """A curated subset (post text + score emphasis), for judge_agent's
    calibration -- needs to understand the whole category-weight landscape
    before grading anything, but ALL 30 examples measured ~5900 tokens of
    system prompt, too much bulk risking diluted attention on the actual
    rubric/draft being graded. Deterministic (first N per category), not
    random like load_example_for_category -- the judge needs a stable,
    consistent bar across calls, unlike the writer which benefits from
    rotation."""
    blocks = _example_blocks()
    parts = []
    for category, examples in blocks.items():
        parts.append(f"## CATEGORY: {category}\n\n" +
                    "\n\n".join(examples[:limit_per_category]))
    return "\n\n---\n\n".join(parts)


def _scene_mood_blocks() -> dict[str, list[str]]:
    """Parses content_config/scene_examples.md into {mood: [example, ...]},
    same "## MOOD: <name>" / "### Example N" delimiter convention as
    _example_blocks() uses for example_posts.md."""
    path = Path(settings.scene_examples_path)
    if not path.exists():
        return {}
    text = path.read_text()
    blocks: dict[str, list[str]] = {}
    for chunk in text.split("## MOOD: ")[1:]:
        name, _, rest = chunk.partition("\n")
        mood_body = rest.split("\n---", 1)[0].strip()
        examples = [e.strip() for e in mood_body.split("### Example ")[1:] if e.strip()]
        blocks[name.strip()] = examples
    return blocks


def load_scene_examples(sample_size: int = 5) -> str:
    """A random SAMPLE of mood archetypes (one random example each), not the
    full file and not a fixed set -- this is what prevents any single
    worked example from becoming a sticky template (see
    scene_examples.md's own docstring for the bug this fixes). Re-sampled
    fresh on every call, same rotation principle as
    load_example_for_category, adapted here since scene_agent doesn't know
    the post's mood ahead of time the way draft_agent knows its category."""
    blocks = _scene_mood_blocks()
    moods = list(blocks.keys())
    random.shuffle(moods)
    chosen = []
    for mood in moods[:sample_size]:
        example = random.choice(blocks[mood])
        _, _, body = example.partition("\n")
        chosen.append(f"MOOD: {mood}\n{body.strip()}")
    return "\n\n".join(chosen)


def load_character_personality(character_id: str) -> str | None:
    """Reads the character's `personality` field straight off character.json.
    Returns None if the character/card doesn't exist -- callers should
    degrade gracefully (character voice is a seasoning, not a requirement)."""
    card_path = (Path(settings.character_forge_v2_path) / "workspace" /
                character_id / "character.json")
    if not card_path.exists():
        return None
    try:
        card = json.loads(card_path.read_text())
    except json.JSONDecodeError:
        return None
    return card.get("personality")
