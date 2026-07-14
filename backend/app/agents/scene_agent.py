"""scene_agent.py -- locked post text -> one terse visual scene instruction.

This feeds directly into character-forge-v2's `forge2 generate <id> "<task>"`,
which appends the scene string to a fixed identity-lock preamble (see
forge2/prompts/templates.py:GENERATE_TEMPLATE) -- character appearance,
clothing, and colors are ALREADY locked by the hero image/card, so this
agent's only job is action + angle + setting + mood, in the same terse,
comma-separated style as character-forge's own validation_battery.yaml
(e.g. "facepalming at a laptop showing an error, frustrated").

This is a harder translation task than it looks: a weak prompt here means
generic or off-target scenes wasting a 15-20 min render, and the user only
gets to review/edit the derived text before that render starts -- so the
few-shot set below deliberately spans different post moods (technical win,
frustration/debugging, celebratory ship, reflective/lessons-learned) rather
than relying on one example to generalize across all of them.

think=true (same reasoning as draft_agent's think=true calls -- this is a
real translation/compression task, not a mechanical one).
"""
from __future__ import annotations

import httpx

from ..config import settings

SYSTEM_PROMPT = """You translate a LinkedIn post's content and mood into ONE terse \
visual scene description for a character illustration that will accompany the post.

The character's appearance, clothing, colors, and face are ALREADY fixed (locked hero \
reference image) -- you must NEVER describe appearance, clothing, or physical traits. \
Your only job is: what is the character DOING, from what ANGLE, in what SETTING, with \
what MOOD/energy. Nothing else.

FORMAT: a single comma-separated phrase, 6-15 words, in this style (these are real \
examples from this system's validated scene library):
- "presenting a chart on a whiteboard, three-quarter view, office"
- "riding a bicycle through a park, side view, sunny day"
- "celebrating with confetti falling, arms raised, front view"
- "facepalming at a laptop showing an error, frustrated"
- "carrying a stack of pizza boxes, slightly overwhelmed"
- "asleep at a desk, night, monitor glow"

HARD CONSTRAINTS:
- No appearance/clothing/color/face description of any kind (already locked elsewhere).
- No rendered text, words, numbers, logos, or UI chrome in the scene -- diffusion models \
render text as garbage, and "a laptop showing an error" is fine but "a laptop showing \
the text ERROR 500: OOM" is not.
- No other people, named companies, or real trademarks/brands.
- One character, one clear action. Not a collage of multiple moments.
- Match the post's actual mood -- a debugging-frustration post should NOT get a \
celebration scene, and a genuine ship/launch post should NOT get a frustrated one.
- Match INTENSITY, not just topic. A milestone/achievement post with real excitement \
(words like "proud", "finally", "crossed", "just going to enjoy this", exclamation \
energy even without exclamation marks) needs a scene with clear celebratory ENERGY -- \
confetti, arms raised, big dynamic pose -- not a muted "smiling at a laptop" scene. \
Save calm/neutral scenes for matter-of-fact technical explainers that don't carry \
emotional weight. Undershooting the energy of a genuinely excited post is as wrong as \
overshooting a calm one.

WORKED EXAMPLES (study how mood maps to scene across different post types):

POST (technical win, calm/explanatory mood): "Cut p95 latency from 800ms to 140ms by \
moving the cache in front of the DB call instead of behind it. Took a week to find, one \
line to fix."
SCENE: "presenting a chart on a whiteboard, three-quarter view, office, calm confident \
energy"

POST (mid-debugging frustration mood): "Spent the whole day chasing a race condition \
that only reproduced under load. Turned out to be a missing mutex around a shared \
counter."
SCENE: "facepalming at a laptop showing an error, frustrated, dim office lighting"

POST (celebratory ship mood): "Shipped the v2 migration tonight after three weeks of \
work. Zero downtime, all tests green. Team pulled together hard for this one."
SCENE: "celebrating with confetti falling, arms raised, front view, evening"

POST (personal milestone, quieter words but genuine excitement -- match the excitement, \
not the word count): "After six months of nights and weekends, my side project just \
crossed 1000 users. No marketing budget, just word of mouth. Tonight I'm just going to \
enjoy this one."
SCENE: "celebrating with arms raised, big smile, confetti falling, front view, evening"

POST (reflective/lessons-learned mood, low external drama): "Twenty years in and the \
lesson that keeps repeating: the bug is almost never where you first look. Slow down, \
reproduce it, THEN theorize."
SCENE: "reading a thick book in an armchair, warm lamp light, thoughtful"

POST (early-stage/exploration mood): "Two days into prototyping a new pipeline. Still \
figuring out the right shape for it, but the early signal is promising."
SCENE: "looking at a wall of sticky notes, back view, thinking"

OUTPUT: return ONLY the scene phrase itself -- no preamble, no quotation marks, no \
explanation, no period at the end."""


async def _call_ollama(client: httpx.AsyncClient, user_content: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "think": True,
        "options": {"temperature": 0.7},
    }
    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def _clean(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        text = text[1:-1].strip()
    return text.rstrip(".")


async def derive_scene(client: httpx.AsyncClient, post_text: str) -> str:
    """Locked post text -> one terse scene instruction (task string for forge2 generate)."""
    user_content = f"POST:\n{post_text}\n\nSCENE:"
    raw = await _call_ollama(client, user_content)
    return _clean(raw)
