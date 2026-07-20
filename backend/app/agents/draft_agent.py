"""draft_agent.py -- brief/clarify -> LinkedIn post text.

Ollama qwen3:14b, direct httpx to /api/chat (no provider abstraction, per this
workspace's convention -- see ai-mentor/backend/app/services/analyzer_service.py
for the pattern this mirrors).

Two thinking modes, deliberately different:
- clarify_turn: think=false. A mechanical classification-plus-question gate,
  not creative work -- keep it fast.
- generate_draft / regenerate_draft: think=true. Real structural reasoning
  (hook strength, what to cut for length, whether the CTA lands) benefits from
  it, and this is where output quality matters most.

As of the content-quality redesign (CONTENT_QUALITY_DESIGN.md), the system
prompt is assembled from three sources instead of one hardcoded string:
user_profile.md (WHO), the character's personality (brand voice seasoning,
optional), and skill.md (HOW -- craft rules). See content_sources.py. This
replaced a hardcoded "20-year software engineer" persona that didn't
generalize -- see linkedin-content-agent-product-pivot memory note.

No feedback-injection here (no few-shot block built from Feedback rows) --
capture-only for this MVP, per explicit instruction; see feedback_service.py.
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import settings
from .content_sources import (load_character_personality, load_example_for_category,
                              load_skill, load_user_profile)
from .taxonomy import CATEGORIES

_FRAMING = """You are a ghostwriter helping a person build their LinkedIn presence. You write \
in THEIR first-person voice, based on what they tell you they worked on."""


def build_system_prompt(character_id: str | None, category: str | None = None) -> str:
    """Assembles the writer's system prompt from user_profile.md + skill.md +
    (optionally) the brand character's personality + (optionally) a
    category-matched example post. Read fresh per call, not cached, since
    these files are meant to be hand-edited between runs.

    Only the ONE matching-category example is injected, deliberately -- all
    six would dilute the writer across styles it doesn't need for this post,
    and defeats the point of category-specific style (see
    example_posts.md's own docstring)."""
    parts = [_FRAMING, f"USER PROFILE:\n{load_user_profile()}"]

    personality = load_character_personality(character_id) if character_id else None
    if personality:
        parts.append(
            "BRAND CHARACTER VOICE SEASONING (subtle influence only -- this shapes tone "
            "and perspective a little, it is NEVER a source of facts and must NEVER "
            f"override the human's authentic first-person experience): {personality}"
        )

    parts.append(load_skill())

    example = load_example_for_category(category) if category else None
    if example:
        parts.append(
            f"STYLE REFERENCE for this post's category ({category}) -- study the shape "
            "and energy of this example, do NOT copy its wording, topic, or hook phrasing "
            "verbatim. CRITICAL: this example may include a specific vivid anecdote or "
            "concrete detail (a remembered incident, a specific number, a quoted moment) as "
            "a STYLE device. That is style guidance only, not permission -- it does NOT mean "
            "you may invent a similarly specific anecdote/incident/detail for THIS post. "
            "Every concrete detail in your output must still come only from the actual brief "
            "and clarification below, per the factual-accuracy rules -- found live, this "
            "exact mistake (inventing a vivid supporting anecdote because the style example "
            f"had one) has happened before:\n{example}"
        )

    return "\n\n".join(parts)


_CATEGORY_LIST = "\n".join(f"- {name}: {desc}" for name, desc in CATEGORIES.items())

CLARIFY_SYSTEM_PROMPT = f"""You collect the raw material for ghostwriting a strong LinkedIn \
post from a rough, informal brief about what a software engineer worked on. Your job is to \
make sure enough REAL material exists before any writing starts -- the writer downstream is \
never allowed to invent a number, tool, incident, or root cause, so anything you don't \
collect here simply cannot appear in the post. Garbage in, garbage out: a thin brief \
produces a thin post, and fixing that is YOUR responsibility, at this stage, by asking.

You are given the post's CATEGORY, which changes what material matters most:
{_CATEGORY_LIST}

A strong post (target 1500-2200 characters) needs SEVERAL real facts, not one: what \
happened, the mechanism/reasoning behind it, at least one concrete number or outcome, what \
was tried that didn't work, and why it mattered. One concrete detail is the bare minimum to \
avoid fabrication -- it is NOT "enough". Judge the brief plus the clarification transcript \
so far against that bar for this category (e.g. a technical_deep_dive needs the root cause \
AND a before/after outcome; a trending_topic needs the user's actual OPINION and at least \
one real experience backing it; a milestone needs the real number/outcome AND what it took \
to get there; a lessons_learned needs the actual lesson AND the real situation it came from).

You get the original brief and the clarification transcript so far (empty on the first \
turn). Decide:
- DONE if the brief + answers now cover enough of that bar to sustain a full post. Do not \
keep asking once the material is genuinely there.
- DONE also if the user's answers signal they have nothing more to give ("that's all I \
remember", "no numbers", two vague/one-line answers in a row) -- do not badger; the system \
will honestly surface thin material downstream instead of padding it.
- Otherwise ask exactly ONE focused question targeting the single MOST valuable missing \
dimension. CRITICAL: most users do not know what "more detail" means until they see an \
example, so your question MUST include a concrete example of the kind of answer that would \
help, in parentheses. For example: "what was the actual before/after number or outcome? \
(e.g. 'latency dropped from 800ms to 140ms', or 'crossed 1000 users')" -- not just "can you \
give more detail?". Before asking, re-read the ORIGINAL BRIEF word by word: never ask for \
something the brief or the transcript already states -- asking for a detail the user already \
gave wastes one of very few questions and tells the user you didn't read their brief.

Never ask more than one question at a time.

Respond with ONLY this JSON object, nothing else:
{{"done": true|false, "question": "..." or null}}"""

_CALIBRATION_EXAMPLE = """WORKED EXAMPLE (study this -- it shows exactly what "don't invent \
facts" means in practice):

BRIEF GIVEN: "trained a character LoRA on mflux (MLX-native, runs fully on-Mac) for a \
mascot character. It kept OOMing at 1024px resolution during training. Dropped to 768px \
which fixed it. Then even at 768px it died around step 143 without --low-ram. Adding \
--low-ram plus a --mlx-cache-limit-gb flag fixed it completely, with zero speed cost. \
Two days of debugging total."

CORRECT -- uses only what was actually stated, connective narration stays general. Note \
the opening does NOT use a "spent X time chasing Y -- here's what fixed it" template -- \
vary hook phrasing every time (see skill.md's hook formula section for why):
"Two OOM crashes, two different root causes, training a character LoRA on my Mac with \
mflux (fully on-device, no cloud GPU).

First one hit at 1024px resolution. Dropping to 768px got past that.

Then at 768px it started dying around step 143 instead -- a slower, sneakier failure \
than the first crash.

The fix was two flags: --low-ram and --mlx-cache-limit-gb. Both crashes gone, and no \
drop in training speed.

Two days of debugging for what turned out to be a one-line fix. Anyone else running \
local LoRA training on Apple Silicon -- what's your go-to for memory issues?"

WRONG -- do NOT do this, even though it reads more "technical":
"...OOM at 30% training completion... capped GPU memory allocation with \
--mlx-cache-limit-gb=4... root cause was unbounded cache growth during gradient \
accumulation..."
None of "30% completion", the value "4", or "unbounded cache growth during gradient \
accumulation" as the stated root cause were in the brief. They sound plausible and \
specific, which is exactly why this mistake is easy to make and exactly why it's not \
allowed -- the post must only claim what was actually said.

SECOND EXAMPLE -- this failure mode is WORST on a thin brief with few real facts, \
because there's a pull to invent detail just to have enough material. Resist it.

BRIEF GIVEN: "fixed an OOM crash in the image pipeline by switching to low-ram mode, \
zero speed cost"
(That's it. No percentage, no phase-of-execution, no named root cause, no duration.)

CORRECT -- shorter and honest beats padded and invented:
"Fixed an OOM crash in our image pipeline today -- switching to low-ram mode cleared \
it, with no speed cost.

No tradeoff I expected going in -- usually a memory fix like this costs you something \
in throughput. Not this time.

Small change, real relief. Anyone else found a memory fix that didn't cost you \
anything in return?"

WRONG -- do NOT do this:
"...OOM at 80% completion during batch processing... reduced memory usage by 40%... \
root cause was unbounded temporary buffer growth during tensor reshaping..."
"80% completion", "batch processing", "40%", and "unbounded temporary buffer growth \
during tensor reshaping" are ALL invented -- the brief never said any of it. A short, \
honest 400-character post is the correct output here, not a padded 900-character one \
built on invented specifics."""


async def _call_ollama(client: httpx.AsyncClient, system_prompt: str, user_content: str,
                       think: bool, json_format: bool = False,
                       temperature: float = 0.7) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "think": think,
        "options": {"temperature": temperature},
    }
    if json_format:
        payload["format"] = "json"

    # 420s, not 180 -- think=true calls with the full assembled prompt have been
    # observed exceeding 180s (found live: a recalibration regenerate_draft call
    # timed out mid-pipeline, stranding the post in "clarifying").
    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=420)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def _strip_wrapping_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        return text[1:-1].strip()
    return text


# Found live: pressed on length, the model appended "---\n(1,120 characters)" to a
# draft that was actually ~870 chars -- claiming compliance instead of achieving
# it. Strip any trailing separator + self-reported character count deterministically.
_TRAILING_META = re.compile(
    r"(?:\n+\s*-{3,}\s*)?\n+\s*\(?~?[\d,]+\s*characters?\)?\s*$", re.IGNORECASE)


def _clean_draft_output(text: str) -> str:
    return _TRAILING_META.sub("", _strip_wrapping_quotes(text)).strip()


def _format_transcript(transcript: list[dict]) -> str:
    if not transcript:
        return "(no clarification turns yet)"
    lines = []
    for turn in transcript:
        lines.append(f"Q: {turn['question']}")
        lines.append(f"A: {turn['answer']}")
    return "\n".join(lines)


async def clarify_turn(client: httpx.AsyncClient, brief: str, transcript: list[dict],
                       category: str) -> dict:
    """One clarify turn. Returns {"done": bool, "question": str | None}."""
    user_content = (f"CATEGORY: {category}\n\n"
                    f"ORIGINAL BRIEF:\n{brief}\n\n"
                    f"CLARIFICATION SO FAR:\n{_format_transcript(transcript)}\n\n"
                    f"QUESTIONS ASKED SO FAR: {len(transcript)} (hard cap "
                    f"{settings.clarify_max_turns} -- spend remaining questions on the "
                    "most valuable gaps)\n\n"
                    "REMINDER: look at the LAST answer above. If it signals the user has "
                    "nothing more to give ('that's all I remember', 'no numbers', 'don't "
                    "remember the details') or is the second vague/one-line answer in a "
                    "row, you MUST respond done=true now -- asking again is badgering and "
                    "will not produce material that doesn't exist.\n\n"
                    "Decide: done, or one more question?")
    raw = await _call_ollama(client, CLARIFY_SYSTEM_PROMPT, user_content,
                             think=False, json_format=True, temperature=0.3)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Malformed JSON from the model -- fail safe to "done" rather than looping.
        return {"done": True, "question": None}
    return {"done": bool(result.get("done", True)),
           "question": result.get("question")}


_ESCALATION_SYSTEM_PROMPT = """A LinkedIn post draft fell short on one or more specific \
quality pillars that REWRITING ALONE cannot fix -- either it needs new material from the \
user, or a different angle on the topic. You'll be given each failing pillar, why it fell \
short (the judge's reasoning), and whether it needs new material or a different angle.

Write ONE short, concrete message to the user covering all the failing pillars given:
- For a pillar needing NEW MATERIAL: ask a specific question with a concrete example of the \
kind of detail that would help, e.g. "what was the actual before/after number or outcome? \
(e.g. 'latency dropped from 800ms to 140ms')" -- never just "can you add more detail?"
- For a pillar needing a DIFFERENT ANGLE: briefly explain why the topic itself scored low \
here, and ask whether they want to reframe it or proceed anyway at the lower score.

Keep it short, direct, and specific to the actual reasons given -- not generic. Respond with \
ONLY the message text, no preamble, no "Here's the message:"."""


async def build_escalation_message(client: httpx.AsyncClient, brief: str, category: str,
                                   failing_pillars: list[dict]) -> str:
    """failing_pillars: [{"pillar": str, "reason": str, "fix_type": "needs_material"|"needs_angle"}, ...]"""
    lines = [f"- {f['pillar']} ({f['fix_type']}): {f['reason']}" for f in failing_pillars]
    user_content = (f"CATEGORY: {category}\n\nORIGINAL BRIEF:\n{brief}\n\n"
                    f"FAILING PILLARS:\n" + "\n".join(lines))
    raw = await _call_ollama(client, _ESCALATION_SYSTEM_PROMPT, user_content,
                             think=False, temperature=0.4)
    return _strip_wrapping_quotes(raw)


_FACT_REMINDER = ("REMINDER: use ONLY facts literally stated above. Do not add any "
                  "number, percentage, tool name, or specific cause that wasn't given. "
                  "If the material is thin, write a short honest post -- do not pad it "
                  "with invented specifics.")

_HOOK_REMINDER = ("REMINDER: do NOT open with \"Spent/spent [time] convinced/chasing X... "
                  "it wasn't / turned out it wasn't\" -- this system has produced that exact "
                  "shape repeatedly and it now reads as a formula, not a hook. If a "
                  "tension-then-reversal hook genuinely fits this material, execute it with "
                  "completely different wording and pacing than that pattern -- or better, "
                  "use a different hook shape entirely (a number/result first, a scene, a "
                  "flat claim). Vary it for real.")

_LENGTH_REMINDER = ("REMINDER on length: this system has been consistently under-shooting -- "
                    "every recent post landed under 850 characters against a 1500-2200 target "
                    "(the 600-900 fallback is ONLY for a genuinely thin brief with nothing more "
                    "to say). Before finalizing, check: does the brief/clarification actually "
                    "contain more real substance than what you've drafted so far -- the "
                    "mechanism/reasoning behind a fix, what was tried and didn't work, what the "
                    "tradeoffs were, what it felt like in the moment, why it mattered? If yes, "
                    "USE it -- elaborate on facts that were actually given, don't compress them "
                    "into the fewest possible words. This is NOT permission to invent new facts "
                    "to hit a length -- it's permission to actually finish explaining the real "
                    "ones instead of stopping at the first complete sentence. Output the post "
                    "text ONLY -- never append a character count, separator line, or any "
                    "meta-commentary about the post after it.")


async def generate_draft(client: httpx.AsyncClient, brief: str,
                         transcript: list[dict], character_id: str | None = None,
                         category: str | None = None) -> str:
    """Initial draft from the brief + clarification transcript."""
    system_prompt = build_system_prompt(character_id, category) + "\n\n" + _CALIBRATION_EXAMPLE
    user_content = (f"BRIEF:\n{brief}\n\n"
                    f"CLARIFICATION:\n{_format_transcript(transcript)}\n\n"
                    f"{_FACT_REMINDER}\n\n{_HOOK_REMINDER}\n\n{_LENGTH_REMINDER}\n\nWrite the LinkedIn post.")
    text = await _call_ollama(client, system_prompt, user_content, think=True,
                              temperature=0.5)
    return _clean_draft_output(text)


async def regenerate_draft(client: httpx.AsyncClient, previous_text: str,
                           instruction: str, character_id: str | None = None,
                           category: str | None = None) -> str:
    """Revise an existing draft per user feedback/instruction (or a judge-pillar
    critique, when called from the recalibration loop)."""
    system_prompt = build_system_prompt(character_id, category) + "\n\n" + _CALIBRATION_EXAMPLE
    user_content = (f"CURRENT DRAFT:\n{previous_text}\n\n"
                    f"REVISION INSTRUCTION:\n{instruction}\n\n"
                    f"{_FACT_REMINDER}\n\n{_HOOK_REMINDER}\n\n{_LENGTH_REMINDER}\n\nWrite the revised LinkedIn post, "
                    "applying the instruction while keeping the structure/voice rules.")
    text = await _call_ollama(client, system_prompt, user_content, think=True,
                              temperature=0.5)
    return _clean_draft_output(text)
