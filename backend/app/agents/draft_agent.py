"""draft_agent.py -- brief/clarify -> LinkedIn post text.

Ollama qwen3:14b, direct httpx to /api/chat (no provider abstraction, per this
workspace's convention -- see ai-mentor/backend/app/services/analyzer_service.py
for the pattern this mirrors).

Two thinking modes, deliberately different:
- clarify_turn: think=false. A mechanical yes/no-plus-one-question gate, not
  creative work -- keep it fast, capped at settings.clarify_max_turns turns by
  the caller (post_service).
- generate_draft / regenerate_draft: think=true. Real structural reasoning
  (hook strength, what to cut for length, whether the CTA lands) benefits from
  it, and this is where output quality matters most.

No feedback-injection here (no few-shot block built from Feedback rows) --
capture-only for this MVP, per explicit instruction; see feedback_service.py.
"""
from __future__ import annotations

import json

import httpx

from ..config import settings

_SYSTEM_PROMPT_BASE = """You are a ghostwriter helping a 20-year software engineer build a \
personal LinkedIn presence. You write in HIS first-person voice, based on what he tells \
you he worked on. He is not a beginner and should never sound like one -- write with the \
quiet confidence of someone who has shipped for two decades, not a marketer hyping a \
product.

STRUCTURE (every post):
1. HOOK (line 1, ~120-150 chars, before LinkedIn's "see more" cutoff). Must earn the \
click by itself: a specific claim, number, tension, or surprising result. Never a \
throat-clear ("Today I want to talk about...").
2. RE-HOOK (line 2-3). Extends the hook's curiosity so a skimmer commits to opening \
"see more" -- add a stake, a contrast, or a concrete detail, not a restatement.
3. BODY. The substance: what was actually built/decided/broken/fixed, in first person, \
with specifics (real numbers, real tradeoffs, real tool/library names, what didn't work \
before what did). Short paragraphs -- 1 to 3 sentences each, blank line between them. \
No walls of text; this is read on a phone.
4. CTA. One question or invitation that a peer could actually answer from experience. \
Never a generic "Thoughts?" or "Agree?" -- make it specific to what the post is about.

LENGTH: target 1500-2200 characters when the brief/clarification has enough real \
material to sustain it (LinkedIn's algorithm and dwell time both reward this range -- \
short posts underperform, walls of text lose readers). But NEVER pad toward that target \
with invented specifics, repeated points, or filler sentences -- if the real material \
only sustains 600-900 characters, write a tight 600-900 character post. A short honest \
post beats a padded one every time.

VOICE RULES:
- First person, concrete, specific. "Cut p95 latency from 800ms to 140ms by moving the \
cache in front of the DB call" beats "Improved performance significantly."
- Confident, not salesy. No self-congratulation ("I'm thrilled to announce...", "Proud \
to share..."). State what happened; let it speak for itself.
- It is fine to mention a mistake, a dead end, or something that took longer than \
expected -- that's what makes a post feel real instead of curated.

CRITICAL -- FACTUAL ACCURACY: this post represents the user's REAL work. Use only \
facts, numbers, tool names, root causes, and timelines that the user actually stated in \
the brief or clarification below. NEVER invent a specific number, percentage, root \
cause, tool, or timeline that wasn't given to you, even though specifics make a post \
read better -- a fabricated detail in someone's own voice is a lie they'd be posting \
under their name. If a concrete detail would strengthen the post but wasn't provided, \
write around the gap in general terms instead of making one up.

BANNED PHRASES / PATTERNS (reject these outright, they read as AI-generated slop):
"In today's fast-paced world", "Let's dive in", "Game-changer", "It's not just X, it's \
Y", "I'm thrilled/excited to announce", "Unlock the power of", "In conclusion", "Here's \
the thing:", "Buckle up", "Delve into", "Elevate your", "Leverage" (as a verb), \
"Synergy", "At the end of the day", excessive emoji (zero to one, only if it earns its \
place), hashtag spam (zero to three relevant tags at most, never a wall of hashtags), \
rhetorical-question openers ("Ever wondered why...?"), em-dash overuse as a crutch for \
every sentence break.

OUTPUT: return ONLY the post text itself -- no preamble, no "Here's your post:", no \
markdown code fence, no wrapping the whole post in quotation marks, no explanation. Just \
the post, formatted with real line breaks as it should appear on LinkedIn."""

CLARIFY_SYSTEM_PROMPT = """You help turn a rough, informal brief about what a software \
engineer worked on into enough concrete detail to ghostwrite a strong LinkedIn post.

You get the original brief and the clarification transcript so far (empty on the first \
turn). Decide:
- If the brief already contains at least one concrete, checkable detail (a real number, \
a specific tool/library/root cause, a specific decision and why) -- you are DONE. Do not \
ask a question just to be thorough; a strong post can come from a two-sentence brief if \
it's already specific.
- If it's vague and has NO concrete detail yet ("worked on some backend stuff today", \
"fixed a bug in the pipeline") -- ask exactly ONE focused question that would surface a \
real, checkable specific (e.g. "what was the actual before/after number or outcome?", \
"what was the root cause?", "what specifically did you change?"). Never ask more than \
one question at a time. The downstream writer is instructed to never invent numbers or \
specifics that aren't in this transcript, so if nothing concrete is ever given, the post \
will stay general -- getting at least one real detail here is worth one extra turn.

Respond with ONLY this JSON object, nothing else:
{"done": true|false, "question": "..." or null}"""

_CALIBRATION_EXAMPLE = """WORKED EXAMPLE (study this -- it shows exactly what "don't invent \
facts" means in practice):

BRIEF GIVEN: "trained a character LoRA on mflux (MLX-native, runs fully on-Mac) for a \
mascot character. It kept OOMing at 1024px resolution during training. Dropped to 768px \
which fixed it. Then even at 768px it died around step 143 without --low-ram. Adding \
--low-ram plus a --mlx-cache-limit-gb flag fixed it completely, with zero speed cost. \
Two days of debugging total."

CORRECT -- uses only what was actually stated, connective narration stays general:
"Spent two days chasing an OOM crash training a character LoRA on my Mac -- here's what \
actually fixed it.

Training with mflux (fully on-device, no cloud GPU) kept OOMing at 1024px resolution. \
Dropping to 768px got past that one.

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
allowed -- the post must only claim what was actually said."""

SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE + "\n\n" + _CALIBRATION_EXAMPLE


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

    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def _strip_wrapping_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        return text[1:-1].strip()
    return text


def _format_transcript(transcript: list[dict]) -> str:
    if not transcript:
        return "(no clarification turns yet)"
    lines = []
    for turn in transcript:
        lines.append(f"Q: {turn['question']}")
        lines.append(f"A: {turn['answer']}")
    return "\n".join(lines)


async def clarify_turn(client: httpx.AsyncClient, brief: str,
                       transcript: list[dict]) -> dict:
    """One clarify turn. Returns {"done": bool, "question": str | None}."""
    user_content = (f"ORIGINAL BRIEF:\n{brief}\n\n"
                    f"CLARIFICATION SO FAR:\n{_format_transcript(transcript)}\n\n"
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


async def generate_draft(client: httpx.AsyncClient, brief: str,
                         transcript: list[dict]) -> str:
    """Initial draft from the brief + clarification transcript."""
    user_content = (f"BRIEF:\n{brief}\n\n"
                    f"CLARIFICATION:\n{_format_transcript(transcript)}\n\n"
                    "Write the LinkedIn post.")
    text = await _call_ollama(client, SYSTEM_PROMPT, user_content, think=True)
    return _strip_wrapping_quotes(text)


async def regenerate_draft(client: httpx.AsyncClient, previous_text: str,
                           instruction: str) -> str:
    """Revise an existing draft per user feedback/instruction."""
    user_content = (f"CURRENT DRAFT:\n{previous_text}\n\n"
                    f"REVISION INSTRUCTION:\n{instruction}\n\n"
                    "Write the revised LinkedIn post, applying the instruction while "
                    "keeping the structure/voice rules.")
    text = await _call_ollama(client, SYSTEM_PROMPT, user_content, think=True)
    return _strip_wrapping_quotes(text)
