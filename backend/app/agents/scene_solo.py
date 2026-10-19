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

What counts as people (precision, 2026-10-19): standalone people words
always count; collective/quantity words ("a group of", "two", "another")
count only when they qualify a person/figure noun -- so "a group of sticky
notes" or "two coffee cups" survive while "a group of colleagues", "a team
of robots" and "the team celebrates" do not.

The word lists are settings (app/config.py scene_people_terms,
scene_collective_terms, scene_figure_qualifiers, scene_figure_nouns).
"""
from __future__ import annotations

import re

from ..config import settings

_PREPOSITIONS = (r"with|alongside|beside|next to|among|amongst|surrounded by|"
                 r"and|to|for|between")
_DETERMINERS = (r"a|an|the|his|her|their|its|some|two|three|four|several|"
                r"a few|a couple of|fellow|other|many|multiple")
_GESTURES = r"shaking hands|high-fiving|fist-bumping|hugging"
_HEADCOUNT = (r"\d+|two|three|four|five|six|seven|eight|nine|ten|twelve|dozens?|"
              r"us|them|you|mine")


def _alternation(terms: list[str]) -> str:
    # Longest first so "team members" wins over "team".
    ordered = sorted({t.strip().lower() for t in terms if t.strip()}, key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)


def _head() -> str | None:
    """Regex for one reference to a person/figure, without surrounding words.

    The rule: standalone people words always count ("colleagues", "the team
    celebrates"); a collective/quantity word only counts when it qualifies a
    person/figure noun ("a group of colleagues", "a team of robots", "two
    engineers") -- "a group of sticky notes", "a cluster of nodes" or "two
    coffee cups" are objects and stay.
    """
    collectives = {t.strip().lower() for t in settings.scene_collective_terms if t.strip()}
    people_terms = [t for t in settings.scene_people_terms if t.strip()]
    plain = _alternation([t for t in people_terms if t.strip().lower() not in collectives])
    collective_people = _alternation([t for t in people_terms
                                      if t.strip().lower() in collectives])
    nouns = _alternation(settings.scene_figure_nouns)
    who = "|".join(x for x in (_alternation(people_terms), nouns) if x)
    collective = _alternation(list(collectives))
    qualifiers = _alternation(settings.scene_figure_qualifiers)

    parts = []
    if plain:
        parts.append(rf"(?<![\w-])(?:{plain})(?![\w-])")
    if collective_people:
        # "team"/"group" on their own are people -- unless "of <something>"
        # follows, in which case the collective rule below decides ("a team
        # of three" / "a group of us" are still people).
        parts.append(rf"(?<![\w-])(?:{collective_people})(?![\w-])"
                     rf"(?!\s+of\s+(?!(?:{_HEADCOUNT})(?![\w-])))")
    if collective and who:
        parts.append(rf"(?<![\w-])(?:{collective})\s+of\s+(?:(?:{_DETERMINERS})\s+)?"
                     rf"(?:[\w-]+\s+)?(?:{who})(?![\w-])")
    if qualifiers and nouns:
        # "two people", "another engineer", "a second copy" -- up to one word between.
        parts.append(rf"(?<![\w-])(?:{qualifiers})\s+(?:[\w-]+\s+)?(?:{nouns})(?![\w-])")
    return "|".join(parts) or None


def _term_pattern() -> re.Pattern | None:
    head = _head()
    return re.compile(head, re.IGNORECASE) if head else None


def people_terms_in(text: str | None) -> list[str]:
    """Every people/duplicate term found in text (empty list -> solo)."""
    pattern = _term_pattern()
    if not text or pattern is None:
        return []
    return [m.group(0) for m in pattern.finditer(text)]


def _rewrite_phrases(text: str) -> str:
    head = _head()
    if head:
        person = rf"(?:(?:{_DETERMINERS})\s+)?(?:[\w-]+\s+)?(?:{head})(?:\s+of\s+[\w-]+)?"
        text = re.sub(rf"\b(?:{_GESTURES})\b(?:\s+with)?(?:\s+{person}(?![\w-]))?",
                      "giving a thumbs-up", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmirror(s?)\b(?!\s+image)", r"window\1", text, flags=re.IGNORECASE)
    if head:
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
