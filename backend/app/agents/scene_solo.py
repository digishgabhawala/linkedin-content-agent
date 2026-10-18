"""scene_solo.py -- keep the mascot the ONLY figure in a scene.

Found live (post dd3415df..., 2026-10-17, lightning profile): a scene ending
"determined, collaborative" rendered TWO copies of the mascot, even with
"solo, only one person" in character-forge-v2's instruction and "two people,
duplicate character" in its negative prompt (which lightning ignores at CFG
1.0). Wording that implies collaborators, an audience, a reflection or a
second copy pulls the image model towards drawing another figure -- and the
only figure it knows how to draw is the mascot.

scene_agent's prompt asks for people-free scenes; this is the deterministic
backstop on its OUTPUT (never on a scene the user typed themselves). There is
no automatic re-ask: compute is one task per step, so the text is rewritten
in place:

1. social gestures that need a second person become a solo gesture
   ("shaking hands with a partner" -> "giving a thumbs-up");
2. a mirror becomes a window (a mirror renders a second copy);
3. "with/alongside/to <people>" phrases and "together" are removed;
4. any comma clause still naming people is dropped.

The word lists are settings (app/config.py scene_people_terms,
scene_figure_qualifiers, scene_figure_nouns).
"""
from __future__ import annotations

import re

from ..config import settings

_PREPOSITIONS = (r"with|alongside|beside|next to|among|amongst|surrounded by|"
                 r"and|to|for|between")
_DETERMINERS = (r"a|an|the|his|her|their|its|some|two|three|four|several|"
                r"a few|a couple of|fellow|other|many|multiple")
_GESTURES = r"shaking hands|high-fiving|fist-bumping|hugging"


def _alternation(terms: list[str]) -> str:
    # Longest first so "team members" wins over "team".
    ordered = sorted({t.strip().lower() for t in terms if t.strip()}, key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)


def _term_pattern() -> re.Pattern | None:
    parts = []
    people = _alternation(settings.scene_people_terms)
    if people:
        parts.append(rf"(?<![\w-])(?:{people})(?![\w-])")
    qualifiers = _alternation(settings.scene_figure_qualifiers)
    nouns = _alternation(settings.scene_figure_nouns)
    if qualifiers and nouns:
        # "two people", "another engineer", "a second copy" -- up to one word between.
        parts.append(rf"\b(?:{qualifiers})\s+(?:[\w-]+\s+)?(?:{nouns})\b")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def people_terms_in(text: str | None) -> list[str]:
    """Every people/duplicate term found in text (empty list -> solo)."""
    pattern = _term_pattern()
    if not text or pattern is None:
        return []
    return [m.group(0) for m in pattern.finditer(text)]


def _rewrite_phrases(text: str) -> str:
    people = _alternation(settings.scene_people_terms)
    if people:
        person = rf"(?:(?:{_DETERMINERS})\s+)?(?:[\w-]+\s+)?(?:{people})(?:\s+of\s+[\w-]+)?"
        text = re.sub(rf"\b(?:{_GESTURES})\b(?:\s+with)?(?:\s+{person}(?![\w-]))?",
                      "giving a thumbs-up", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmirror(s?)\b(?!\s+image)", r"window\1", text, flags=re.IGNORECASE)
    if people:
        text = re.sub(rf"\s*\b(?:{_PREPOSITIONS})\s+{person}(?![\w-])", "", text,
                      flags=re.IGNORECASE)
    text = re.sub(r"\s*\b(?:together|collaboratively|side\s+by\s+side)\b", "", text,
                  flags=re.IGNORECASE)
    return text


def _tidy(text: str) -> str:
    clauses = [re.sub(r"\s+", " ", c).strip(" .;") for c in text.split(",")]
    return ", ".join(c for c in clauses if c)


def make_solo(text: str | None) -> str | None:
    """text with every people/duplicate reference removed. Unchanged (byte for
    byte) when it is already solo; may come back empty when nothing else was
    left -- the caller picks a fallback for its field."""
    if not text or not people_terms_in(text):
        return text
    rewritten = _rewrite_phrases(text)
    kept = [c for c in rewritten.split(",") if not people_terms_in(c)]
    return _tidy(",".join(kept))
