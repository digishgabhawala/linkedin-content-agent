"""taxonomy.py -- category + pillar definitions shared across category_agent,
judge_agent, and post_service. See CONTENT_QUALITY_DESIGN.md for the design
this implements.

Pillar weights below are reasonable starting defaults, NOT calibrated against
real data -- the design doc explicitly defers exact numbers until there's a
body of real drafts to tune against. Treat these as "good enough to be
functional," expect to revisit.
"""
from __future__ import annotations

CATEGORIES = {
    "technical_deep_dive": "A specific problem solved, architecture decision, "
                           "or debugging story -- credibility with a technical audience "
                           "matters more than broad reach.",
    "trending_topic": "Reacting to something currently happening in the industry/tools "
                      "landscape -- timeliness and reach matter most.",
    "lessons_learned": "Career wisdom, retrospective, reflective -- low external drama, "
                       "credibility-driven.",
    "milestone": "Shipped something, hit a number, launched -- genuine excitement, "
                 "celebratory energy.",
    "exploration": "Early-stage, still figuring something out, prototyping.",
    "industry_opinion": "A broader take not tied to one specific personal artifact.",
}

# GATE pillars: must clear GATE_THRESHOLD, never averaged/traded against
# anything else. voice_authenticity is rewrite-fixable (recalibration can try
# again); factual_integrity is NOT (no rewrite invents a fact that wasn't
# given) -- see FIX_TYPE below.
GATE_PILLARS = ["factual_integrity", "voice_authenticity"]
GATE_THRESHOLD = 9.0

# Optimization pillars: scored, weighted per category, recalibrated toward
# higher (up to settings.max_recalibration_passes).
OPTIMIZATION_PILLARS = [
    "hook", "structure", "cta", "length_fit", "character_consistency",
    "topic_resonance", "profile_fit", "market_timeliness",
]

RECALIBRATION_THRESHOLD = 6.5

# How a low score on a given pillar should be handled -- not all failures are
# fixable by rewriting alone (see CONTENT_QUALITY_DESIGN.md's pillar table).
FIX_TYPE = {
    "factual_integrity": "needs_material",
    "voice_authenticity": "rewrite",
    "hook": "rewrite",
    "structure": "rewrite",
    "cta": "rewrite",
    "length_fit": "rewrite",
    "character_consistency": "rewrite",
    "topic_resonance": "needs_angle",
    "profile_fit": "needs_material",
    "market_timeliness": "needs_angle",
}

# category -> {pillar: weight}, weights sum to 1.0 per category.
PILLAR_WEIGHTS = {
    "technical_deep_dive": {
        "hook": 0.15, "structure": 0.15, "cta": 0.10, "length_fit": 0.10,
        "character_consistency": 0.05, "topic_resonance": 0.10,
        "profile_fit": 0.25, "market_timeliness": 0.10,
    },
    "trending_topic": {
        "hook": 0.20, "structure": 0.10, "cta": 0.10, "length_fit": 0.10,
        "character_consistency": 0.05, "topic_resonance": 0.20,
        "profile_fit": 0.10, "market_timeliness": 0.15,
    },
    "lessons_learned": {
        "hook": 0.15, "structure": 0.15, "cta": 0.15, "length_fit": 0.10,
        "character_consistency": 0.05, "topic_resonance": 0.10,
        "profile_fit": 0.25, "market_timeliness": 0.05,
    },
    "milestone": {
        "hook": 0.20, "structure": 0.10, "cta": 0.10, "length_fit": 0.10,
        "character_consistency": 0.15, "topic_resonance": 0.15,
        "profile_fit": 0.15, "market_timeliness": 0.05,
    },
    "exploration": {
        "hook": 0.15, "structure": 0.15, "cta": 0.15, "length_fit": 0.10,
        "character_consistency": 0.05, "topic_resonance": 0.15,
        "profile_fit": 0.20, "market_timeliness": 0.05,
    },
    "industry_opinion": {
        "hook": 0.20, "structure": 0.10, "cta": 0.15, "length_fit": 0.10,
        "character_consistency": 0.05, "topic_resonance": 0.20,
        "profile_fit": 0.10, "market_timeliness": 0.10,
    },
}


def weighted_score(category: str, pillar_scores: dict[str, float]) -> float:
    weights = PILLAR_WEIGHTS.get(category, PILLAR_WEIGHTS["technical_deep_dive"])
    return sum(pillar_scores.get(p, 0.0) * w for p, w in weights.items())
