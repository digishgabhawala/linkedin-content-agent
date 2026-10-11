"""Parsers turn a worker's raw text into step results -- and fail safe on bad output."""
import json

from app.agents.category_agent import parse_category
from app.agents.draft_agent import parse_clarify, parse_draft, parse_escalation
from app.agents.judge_agent import parse_judge
from app.agents.scene_agent import parse_scene
from app.agents.taxonomy import GATE_PILLARS, OPTIMIZATION_PILLARS


def test_category_parses_known_and_defaults_unknown():
    assert parse_category('{"category": "lessons_learned"}') == "lessons_learned"
    assert parse_category('{"category": "nonsense"}') == "technical_deep_dive"
    assert parse_category("not json") == "technical_deep_dive"


def test_clarify_question_and_malformed_means_done():
    assert parse_clarify('{"done": false, "question": "Which team?"}') == {
        "done": False, "question": "Which team?"}
    assert parse_clarify("garbage") == {"done": True, "question": None}


def test_draft_and_escalation_cleanup():
    assert parse_draft("Great post.\n---\n(1,120 characters)") == "Great post."
    assert parse_draft('"Great post."') == "Great post."
    assert parse_escalation('"Can you add the numbers?"') == "Can you add the numbers?"


def test_judge_fails_safe_to_zero_for_missing_pillars():
    first = GATE_PILLARS[0]
    scores = parse_judge(json.dumps({first: {"score": 9, "reason": "solid"}}))
    assert scores[first] == {"score": 9.0, "reason": "solid"}
    assert set(scores) == set(GATE_PILLARS) | set(OPTIMIZATION_PILLARS)
    assert all(scores[p]["score"] == 0.0 for p in scores if p != first)


def test_scene_falls_back_on_incomplete_output():
    assert parse_scene('{"action": "x"}')["setting_name"] is None
    full = '{"action": "a", "setting_name": "office", "setting_detail": "d", "angle": "g", "mood": "m"}'
    assert parse_scene(full)["setting_name"] == "office"
