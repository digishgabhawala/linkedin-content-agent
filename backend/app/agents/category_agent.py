"""category_agent.py -- brief -> category (see taxonomy.py).

Category drives pillar weighting in judge_agent (a technical deep-dive and a
trending hot-take shouldn't be graded on the same curve) and is inferred once,
early, then stored on the Post -- not re-inferred at scoring time.

think=false: this is a classification call, not creative work, keep it fast.
"""
from __future__ import annotations

from ..services.llm_client import LLMRequest
from .taxonomy import CATEGORIES

_CATEGORY_LIST = "\n".join(f"- {name}: {desc}" for name, desc in CATEGORIES.items())

SYSTEM_PROMPT = f"""Classify a LinkedIn post brief into exactly ONE of these categories:

{_CATEGORY_LIST}

Respond with ONLY this JSON object, nothing else:
{{"category": "<one of the category names above, exactly as written>"}}"""


def build_category_request(brief: str) -> LLMRequest:
    return LLMRequest([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"BRIEF:\n{brief}"},
    ], temperature=0.2, reasoning=False, response_format="json")


def parse_category(raw: str) -> str:
    import json
    try:
        result = json.loads(raw)
        category = result.get("category", "") if isinstance(result, dict) else ""
    except json.JSONDecodeError:
        category = ""

    return category if category in CATEGORIES else "technical_deep_dive"
