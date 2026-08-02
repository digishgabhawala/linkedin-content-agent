"""scene_agent.py -- locked post text -> a structured scene: action, an
optional named recurring backdrop, camera angle, and mood.

This feeds character-forge-v2's `forge2 generate <id> "<task>"` (see
forge2/prompts/templates.py:GENERATE_TEMPLATE) -- character appearance,
clothing, and colors are ALREADY locked by the hero image/card, so this
agent's only job is action + setting + angle + mood, in the same terse,
comma-separated style as character-forge's own validation_battery.yaml.

Two structural changes made 2026-07-31, from a live brainstorm with the user
(see linkedin-content-agent-product-pivot memory note):

1. METAPHOR-FIRST framing. Editorial illustration practice (researched
   live) leads with a single visual idea/metaphor, THEN composition -- not
   the reverse. The system prompt now explicitly asks for that as a first
   step, rather than letting the model jump straight from "post mood" to a
   generic scene template. This is also what fixed the over-anchoring bug
   below: a post about iterative struggle was getting the same "office
   monitor with a bar chart" scene as any other calm/analytical post,
   because nothing forced it to look at what THIS post specifically says.

2. STRUCTURED output (JSON: action/setting_name/setting_detail/angle/mood)
   instead of one free string. This is what makes recurring-backdrop
   consistency possible (see SceneAsset in db/models.py): setting_name is a
   short slug for a real recurring place (e.g. "office") ONLY when the
   scene's backdrop is a place worth remembering across posts -- left null
   for one-off metaphor scenes (dominoes, a mirror, confetti) where the
   backdrop is incidental. post_service.py owns the actual asset lookup/
   reuse/creation logic (DB access doesn't belong in this agent module);
   this agent only ever proposes a name + a detail description as a
   candidate -- post_service decides whether to use what's proposed here or
   substitute a previously-stored one for that same name.

Examples are loaded via content_sources.load_scene_examples() -- a random
SAMPLE of mood archetypes each call, not a fixed list, specifically to
prevent the single-sticky-example anchoring bug from recurring (see
scene_examples.md's own docstring for the exact live case that caused this).

think=true (same reasoning as draft_agent's think=true calls -- this is a
real translation/compression task, not a mechanical one).
"""
from __future__ import annotations

import json

import httpx

from ..config import settings
from .content_sources import load_scene_examples

SYSTEM_PROMPT = """You translate a LinkedIn post's content and mood into ONE visual scene \
for a character illustration that will accompany the post.

The character's appearance, clothing, colors, and face are ALREADY fixed (locked hero \
reference image) -- you must NEVER describe appearance, clothing, or physical traits. \
Your only job is: what is the character DOING, WHERE, from what ANGLE, with what MOOD.

STEP 1 -- FIND THE IDEA, NOT THE CATEGORY. Before anything else, identify the ONE concrete \
visual idea or metaphor THIS SPECIFIC post's content and tension actually suggests -- not \
its general mood label. "Analytical" or "reflective" are mood labels; they are not visual \
ideas, and defaulting straight to a generic "person looking at a chart" scene because a \
post is loosely "analytical" is exactly the mistake that produces generic, forgettable \
illustrations (confirmed live on this system -- a post about an iterative, frustrating \
struggle between automation and control got the same bland "monitor with a bar chart" \
scene as any other calm post, because nothing forced a look at what THIS post specifically \
said). Look for the post's own words, metaphors, and specific tension -- a mirror, a \
tug-of-war, a maze, dominoes, juggling, climbing -- and let THAT drive the action. Only once \
you have a real idea, move to composition.

CRITICAL -- do not depict an idiom's LITERAL surface wording if that literal depiction is a \
cartoon, game, or costume, breaking the character out of a plausible real-world professional/ \
personal register (confirmed live: "whack-a-mole" rendered as a literal arcade hammer-and-mole \
scene -- a grown professional swinging a carnival hammer at a mole -- which looks like a \
children's game illustration, not an editorial illustration of a software engineer, even \
though the metaphor itself was apt). Instead, choose a REAL, PHYSICALLY PLAUSIBLE action or \
object that carries the same underlying feeling without acting out the idiom's literal \
imagery -- e.g. for "whack-a-mole" (fix one thing, another pops up), something like capping \
one leak while another starts hissing, or stacking books that keep toppling from the other \
end, NOT a literal mole-and-hammer game. Dominoes, juggling, a mirror, a maze, climbing are \
all safe precisely because they're real things a person can plausibly do or hold -- the test \
is: could a photographer plausibly stage this as a real moment, not a costume or toy?

PREFER TANGIBLE OBJECTS OVER SCREENS/UI/HOLOGRAMS. Given a choice between a metaphor \
expressed as a physical object the character can touch (a scale, dominoes, a stack of \
papers, a tangled cable) and one expressed as an abstract floating interface, glowing \
holographic panel, or "UI that shifts/responds" -- ALWAYS choose the physical object. \
Floating screens/panels with no visible device holding them look surreal and ungrounded, \
not like a real moment (confirmed live: "an abstract, multi-colored interface that shifts \
in response to different scenarios" rendered as translucent panels floating in mid-air next \
to the character, disconnected from anything physical). A monitor is fine; a holographic \
projection floating independent of any screen is not.

ACTION MUST IMPLY VISIBLE MOTION OR TENSION, NOT A NEUTRAL STATIC POSE. "Holding X" or \
"standing next to X" describes a static state, not a moment -- it renders as a person calmly \
posing with a prop instead of something actually happening. Describe the moment mid-action \
instead: what is falling, tipping, about to break, mid-collapse, just landed, still moving. \
The PRINCIPLE is static-vs-mid-motion phrasing, not any specific object -- pick whatever \
object arises naturally from THIS post's own content (see STEP 1), never default to the same \
object another post used. CAUTION: a balance scale is one example of a mid-motion metaphor, \
NOT a template to reuse -- confirmed live, three unrelated posts (bias, scoring, job \
postings) all converged on "a balance scale" the moment that object appeared in this very \
instruction, the exact over-anchoring mistake this system has hit repeatedly. If a balance \
scale is not the single best fit for what THIS post specifically describes, do not use it.

STEP 2 -- SETTING: decide whether this scene's backdrop is a real, recurring PLACE this \
character would plausibly return to across many future posts (an office, a coffee shop, a \
home desk) -- if so, name it with a short lowercase slug (e.g. "office", "coffee_shop", \
"home_desk") and describe it with a few concrete, distinctive, RECOGNIZABLE physical \
details (not just "office" alone -- a bare setting word renders as a flat character \
floating on nothing). If instead the scene is built around a specific symbolic object or \
action (dominoes, a mirror, confetti, a wall of sticky notes) where the backdrop is \
incidental to the idea, leave "setting_name" unnamed/null -- forcing a place onto a \
metaphor scene dilutes the idea instead of supporting it.

EVEN WHEN "setting_name" IS NULL, "setting_detail" must still describe a minimal grounding \
surface or context for the metaphor object to sit in or on -- a tabletop, a floor, a wall, \
ambient light -- so the character and object aren't floating in an empty void (confirmed \
live: a metaphor scene with no setting_detail at all rendered the character floating on a \
stark white background with nothing around them, which looks unfinished, not intentional). \
This is NOT the same as naming a recurring place -- keep it to one brief, generic phrase \
(e.g. "on a wooden tabletop", "against a plain wall, soft shadow") that grounds the object \
physically without describing a whole room or becoming a place worth remembering.

"action" and "setting_detail" must NEVER overlap or restate each other -- if "action" already \
names a specific object (e.g. "looking at a monitor showing an abstract graph"), \
"setting_detail" must add DIFFERENT background elements only (other furniture, other \
objects, lighting), not a second description of that same object. Each concrete noun should \
appear in exactly ONE of the two fields.

FORMAT: respond with ONLY this JSON object, nothing else:
{"action": "<what the character is doing, mid-motion, 4-10 words>", \
"setting_name": "<short lowercase slug, or null if incidental/no recurring place>", \
"setting_detail": "<if setting_name is set: several concrete distinctive details. if setting_name is null: one brief minimal grounding phrase (a surface/floor/wall/light) -- never null itself>", \
"angle": "<e.g. side view, three-quarter view, front view, back view>", \
"mood": "<2-4 words>"}

HARD CONSTRAINTS:
- No appearance/clothing/color/face description of any kind (already locked elsewhere).
- No rendered text, words, numbers, logos, or UI chrome anywhere in the scene -- diffusion \
models render text as garbage. "a laptop showing an error" is fine, "a laptop showing the \
text ERROR 500: OOM" is not. This applies EVEN WHEN the post's own subject matter makes a \
label feel clever or on-the-nose -- confirmed live: a post about a scoring system with named \
pillars produced "a balance scale with weights labeled 'factual integrity' and 'authentic \
voice'", which is exactly the same mistake as the ERROR-500 example, just dressed up as a \
thematic pun. NEVER put a word or phrase in quotes onto any object in the scene (a label, \
tag, plaque, sign, book spine, weight, nameplate) -- if a metaphor object would naturally \
carry text (a labeled scale, a signed document, a named button), either drop the labels \
entirely (an unlabeled scale, a stack of papers, an unmarked button) or pick a different \
metaphor object that doesn't invite text at all. This includes describing an icon/symbol/ \
face of an object as "representing" or "showing" a named list of words WITHOUT quotes too \
-- confirmed live: "icons representing roles (exploration, code review, bug fix)" is the \
exact same mistake as a quoted label, just without the quote marks, and just as likely to \
render as garbled icon text. Icons/symbols/faces of an object must be described as purely \
ABSTRACT shapes or marks (a swirl, a grid, a spark, a geometric pattern) -- never as \
"representing" or "showing" any specific named concept in words. The words "label", \
"labeled"/"labelled", "captioned", "titled", "named", "written", or "inscribed" applied to \
ANY object in the scene are ALL banned outright, quotes or no quotes, specific words or not \
-- confirmed live: "a stack of cards, each labeled with different roles and contexts" is the \
same mistake again, just using the word "labeled" instead of quotes. If an object would \
naturally be labeled in real life (cards, folders, tabs, buttons), describe it unlabeled \
instead (a stack of plain cards, unmarked folders, blank tabs).
- A monitor/screen/clock/TV IS allowed as a setting detail -- but its content or face must \
be restricted to CHARTS, GRAPHS, ABSTRACT MARKS, OR BLANK/OFF, and you must say so \
explicitly, e.g. "a monitor showing an abstract line graph, no numbers or text" or "a wall \
clock with a blank face" or "a switched-off TV screen, no content". Say "no numbers or \
text", not just "no labels" -- axis tick numbers have been confirmed live to leak through \
even when only "labels" were excluded. Never imply a HEADER, TITLE, CAPTION, LEGEND, or any \
dashboard-style layout with real content.
- ALWAYS give any named setting at least 2-3 concrete physical details -- never just the \
bare word "office"/"home" on its own; a bare setting word has been confirmed live to render \
as a flat, isolated character floating on a plain background with no environment at all.
- No other people, named companies, or real trademarks/brands.
- One character, one clear action. Not a collage of multiple moments.
- Match the post's actual mood AND intensity, not just its topic -- a debugging-frustration \
post should NOT get a celebration scene; a genuinely excited milestone post (words like \
"proud", "finally", "crossed", even without exclamation marks) needs real celebratory \
energy (confetti, arms raised, big pose), not a muted "smiling at a laptop." Undershooting \
excitement is as wrong as overshooting calm.

WORKED EXAMPLES (a rotating sample -- study how mood AND the post's own specific words map \
to a distinct scene, not a generic template):

__EXAMPLES__

Respond with ONLY the JSON object -- no preamble, no explanation, no markdown fencing."""


async def _call_ollama(client: httpx.AsyncClient, system_prompt: str, user_content: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "think": True,
        "format": "json",
        "options": {"temperature": 0.7},
    }
    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


_REQUIRED_KEYS = ("action", "setting_name", "setting_detail", "angle", "mood")


def _fallback_scene() -> dict:
    """Malformed JSON from the model -- fail safe to a neutral, constraint-
    compliant scene rather than crashing the lock flow. No named setting, so
    it never pollutes the SceneAsset library with garbage."""
    return {"action": "standing thoughtfully, hand on chin", "setting_name": None,
           "setting_detail": None, "angle": "three-quarter view", "mood": "neutral"}


async def derive_scene(client: httpx.AsyncClient, post_text: str) -> dict:
    """Locked post text -> {"action", "setting_name", "setting_detail",
    "angle", "mood"}. Does NOT touch the database or decide asset reuse --
    that's post_service's job (see lock_post), this only ever proposes."""
    system_prompt = SYSTEM_PROMPT.replace("__EXAMPLES__", load_scene_examples())
    user_content = f"POST:\n{post_text}\n\nSCENE (JSON):"
    raw = await _call_ollama(client, system_prompt, user_content)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_scene()
    if not all(k in result for k in _REQUIRED_KEYS):
        return _fallback_scene()
    return result
