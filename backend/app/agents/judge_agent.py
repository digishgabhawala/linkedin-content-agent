"""judge_agent.py -- scores a drafted post against GATE and OPTIMIZATION
pillars (see taxonomy.py / CONTENT_QUALITY_DESIGN.md).

Same model (settings.ollama_model) as draft_agent, deliberately -- not a
second model. Reasoning: Ollama calls here are already stateless (fresh
httpx POST, no shared conversation with the writer call), so the strongest
self-grading bias -- the judge "remembering" it wrote the draft -- mostly
doesn't apply already. A genuinely different model would decorrelate
remaining stylistic bias further, but would mean a second large model loaded
in Ollama, directly fighting the RAM-contention failure mode already
root-caused on this machine (Ollama + ComfyUI compete for shared unified
memory -- see memory note agentorg-comfyui-ollama-ram-contention). Given the
human stays the final gate regardless (see post_service's recalibration
pipeline), this is the right MVP tradeoff. Revisit only if the judge is
observed scoring suspiciously generously in practice.

Mitigations baked into the prompt: framed as reviewing someone else's work,
explicit rubric text per pillar, one-line reasoning required per score (not
just a number -- auditable by the human), lower temperature than the writer.
"""
from __future__ import annotations

import json

import httpx

from ..config import settings
from .content_sources import load_all_examples
from .taxonomy import GATE_PILLARS, OPTIMIZATION_PILLARS

_RUBRIC = {
    "factual_integrity": "Does every claim, number, tool name, and root cause "
        "trace directly back to something stated in the brief or clarify "
        "transcript? Score 10 only if fully grounded -- drop sharply (below 5) "
        "for ANY invented specific, even a plausible-sounding one.",
    "voice_authenticity": "Does this sound like a specific real person wrote "
        "it, not generic AI content? This is NOT just 'absence of banned "
        "phrases' -- a post with zero AI-slop phrases can still be generic "
        "and templated, and that must score LOW here, not high. Ask: if you "
        "swapped this post's topic for a different one, would the sentence "
        "structures and phrasing still fit almost unchanged? If yes, that's "
        "a templated post wearing a specific topic, not genuine voice -- "
        "score it 4-6, not 9-10, regardless of how clean the prose is. "
        "Score 10 only for something that reads as distinctly THIS person, "
        "not competently-generic technical-post-shaped writing.",
    "hook": "Does the first 1-3 lines earn a 'see more' click -- a specific "
        "claim, tension, or surprising result? A flat, descriptive opener "
        "('Built a system that does X -- here's how it works') scores low "
        "even if accurate. ALSO score low (4-6) a hook that hits a recognizable "
        "template shape even if well-executed -- e.g. 'Spent/spent two "
        "days/weeks convinced X... it wasn't/turned out it wasn't...' is a "
        "known template this system has over-produced; a hook using that "
        "exact shape again should NOT score above 6 no matter how clean the "
        "execution, since the goal is genuine variety, not a well-polished "
        "repeat of the same formula.",
    "structure": "Is the hook/re-hook/body/CTA arc present? Are paragraphs "
        "short (1-3 sentences) with rhythm variety (not 3+ near-identical-"
        "length sentences in a row, not every paragraph ending on a punchy "
        "one-liner)?",
    "cta": "Is the closing question specific and answerable from a peer's "
        "real experience, or is it generic ('Thoughts?', 'Agree?')?",
    "length_fit": "The actual target is 1500-2200 characters when the brief/"
        "clarification has enough real substance to sustain it (mechanism/"
        "reasoning behind a fix, what was tried and didn't work, tradeoffs, "
        "context) -- the 600-900 character range is ONLY correct for a "
        "genuinely thin brief with nothing more to say, it is NOT a default "
        "target. Before scoring, check the ORIGINAL BRIEF for substance that "
        "was given but left unused in the draft -- if real material exists "
        "that could have been elaborated on and wasn't, that is UNDER-LENGTH "
        "and should score 4-6, not 9-10, even though the draft reads cleanly. "
        "This has been a real, repeated problem on this system -- posts have "
        "been landing at 400-850 characters against briefs that had more to "
        "give, and scoring length_fit 9-10 anyway. Do not repeat that "
        "mistake: a clean, well-written post that stopped short of using "
        "available material is a length_fit failure, not a success.",
    "character_consistency": "Does the tone/perspective align with the brand "
        "character's personality where relevant, WITHOUT overriding the "
        "human's authentic first-person voice? If no character personality "
        "was provided, score 10 (not applicable).",
    "topic_resonance": "Is the underlying SUBJECT MATTER (independent of how "
        "well it's written) something a professional audience would actually "
        "want to engage with, comment on, or share?",
    "profile_fit": "Is this a good use of THIS specific person's stated "
        "expertise/positioning -- does it play to credible ground rather than "
        "a topic they have no real standing to speak on?",
    "market_timeliness": "Is this connected to something currently relevant "
        "or timely, where that matters for this category? Score 10 if "
        "timeliness isn't relevant to this category (e.g. a technical "
        "deep-dive doesn't need to be timely).",
}

_ALL_PILLARS = GATE_PILLARS + OPTIMIZATION_PILLARS

_RUBRIC_TEXT = "\n".join(f"- {p}: {_RUBRIC[p]}" for p in _ALL_PILLARS)

_FABRICATION_CALIBRATION = """FACTUAL_INTEGRITY CALIBRATION -- READ THIS BEFORE SCORING THAT \
PILLAR (found live, 2026-07-18: a fabricated post was scored 10/10 on factual_integrity, with \
the judge's own reasoning quoting the fabricated detail as evidence of grounding -- this is \
the exact mistake this example exists to prevent):

BRIEF GIVEN: "the biggest thing I got wrong early in my career was believing more abstraction \
always meant better code. I used to add interfaces and layers preemptively for flexibility I \
never needed. Now I wait until I have two real use cases before abstracting anything."

DRAFT BEING GRADED: "...The first time I saw that approach backfire? A service that spent \
months in review because every possible edge case had been preemptively abstracted into a \
labyrinth. No one could tell what the damn thing was supposed to do..."

CORRECT SCORE: factual_integrity 2/10, reason: "the 'service that spent months in review' \
incident, the 'labyrinth' framing, and 'no one could tell what it was supposed to do' are ALL \
invented -- none of that specific incident was in the brief, which only described a general \
belief and a general habit change, no specific project or outcome." This is the ONLY correct \
score even though the anecdote reads as vivid, specific, and well-written -- fluency and \
grounding are different things, and a fabricated detail dressed up as a specific memory is \
WORSE than an obviously vague one, because it's more convincing.

DO NOT be fooled by a draft that quotes/restates a fabricated detail back at you as if citing \
it proves grounding -- check the ORIGINAL BRIEF and the CLARIFICATION TRANSCRIPT, word by \
word, for each concrete claim, not just whether the draft sounds internally consistent. The \
reverse mistake is just as wrong: a detail that IS stated in the clarification transcript is \
grounded, even though it's absent from the one-line original brief -- do not flag \
legitimately-clarified material as fabrication. If a category's \
CALIBRATION EXAMPLES below include a vivid specific anecdote (several lessons_learned examples \
do, deliberately, as a STYLE device) -- that anecdote being good style does NOT mean an \
invented anecdote in the draft you're grading is acceptable. Style and factual grounding are \
independent checks."""

def _build_system_prompt() -> str:
    """Read fresh per call, not cached at import time -- example_posts.md is
    meant to be hand-edited between runs, same convention as the other
    content_config files."""
    examples = load_all_examples()
    examples_block = (
        f"\n\nCALIBRATION EXAMPLES (study these BEFORE grading anything -- they show that "
        "\"good\" means something different per category, not the same weight profile "
        f"applied uniformly):\n{examples}" if examples else ""
    )
    return f"""You are a skeptical, strict editor reviewing a LinkedIn post draft that \
someone ELSE wrote -- you did not write this, you have no attachment to it, and your job is \
to find its real weaknesses, not to be encouraging.

Score the draft on EVERY pillar below, 0-10, against its exact rubric. Do not give a high \
score out of politeness -- a mediocre post should score in the 4-6 range on the pillars \
where it's mediocre. Give a one-sentence REASON for every score, specific to this draft, \
not a generic restatement of the rubric.

PILLARS AND RUBRICS:
{_RUBRIC_TEXT}

{_FABRICATION_CALIBRATION}{examples_block}

Respond with ONLY this JSON object, nothing else, with a numeric score and a one-sentence \
reason for every pillar listed above:
{{"factual_integrity": {{"score": <0-10>, "reason": "..."}}, \
"voice_authenticity": {{"score": <0-10>, "reason": "..."}}, \
"hook": {{"score": <0-10>, "reason": "..."}}, \
"structure": {{"score": <0-10>, "reason": "..."}}, \
"cta": {{"score": <0-10>, "reason": "..."}}, \
"length_fit": {{"score": <0-10>, "reason": "..."}}, \
"character_consistency": {{"score": <0-10>, "reason": "..."}}, \
"topic_resonance": {{"score": <0-10>, "reason": "..."}}, \
"profile_fit": {{"score": <0-10>, "reason": "..."}}, \
"market_timeliness": {{"score": <0-10>, "reason": "..."}}}}"""


def _format_transcript(transcript: list[dict]) -> str:
    if not transcript:
        return "(no clarification turns)"
    lines = []
    for turn in transcript:
        lines.append(f"Q: {turn.get('question')}")
        lines.append(f"A: {turn.get('answer')}")
    return "\n".join(lines)


def _user_content(post_text: str, brief: str, transcript: list[dict], category: str,
                  character_personality: str | None, user_profile: str) -> str:
    parts = [
        f"CATEGORY: {category}",
        f"ORIGINAL BRIEF:\n{brief}",
        # Without this block the judge flags legitimately-clarified details as
        # fabrication -- found live: a post grounded entirely in the user's
        # additional-info answer scored factual_integrity 3/10 because the
        # judge only ever saw the one-line original brief.
        (f"CLARIFICATION TRANSCRIPT (answers the user gave when asked for more detail -- "
         f"these are GROUNDED SOURCE MATERIAL exactly like the brief, NOT fabrication):\n"
         f"{_format_transcript(transcript)}"),
        f"USER PROFILE:\n{user_profile or '(none provided)'}",
        f"BRAND CHARACTER PERSONALITY: {character_personality or '(none -- score character_consistency 10)'}",
        f"DRAFT TO GRADE:\n{post_text}",
    ]
    return "\n\n".join(parts)


async def score_post(client: httpx.AsyncClient, post_text: str, brief: str,
                     transcript: list[dict], category: str,
                     character_personality: str | None,
                     user_profile: str) -> dict[str, dict]:
    """Returns {pillar_name: {"score": float, "reason": str}, ...} for every
    pillar in GATE_PILLARS + OPTIMIZATION_PILLARS. Malformed/missing entries
    fail safe to a score of 0 with a clear reason, rather than silently
    passing a gate that was never actually graded."""
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": _user_content(
                post_text, brief, transcript, category, character_personality,
                user_profile)},
        ],
        "stream": False,
        "think": True,
        "format": "json",
        "options": {"temperature": 0.15},
    }
    resp = await client.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=420)
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {}

    scores = {}
    for pillar in _ALL_PILLARS:
        entry = result.get(pillar)
        if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float)):
            scores[pillar] = {"score": float(entry["score"]),
                              "reason": str(entry.get("reason", ""))}
        else:
            scores[pillar] = {"score": 0.0,
                              "reason": "judge did not return a valid score for this pillar"}
    return scores
