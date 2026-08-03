from app.services.post_service import (
    _apply_length_fit,
    _length_fit_score,
    _material_chars,
)


def test_material_chars_counts_brief_plus_answered_transcript():
    brief = "x" * 50
    transcript = [
        {"question": "q1", "answer": "y" * 20},
        {"question": "q2", "answer": None},  # unanswered -- contributes 0
    ]
    assert _material_chars(brief, transcript) == 70


def test_length_fit_score_bands():
    assert _length_fit_score(0) == 3.0
    assert _length_fit_score(599) == 3.0
    assert _length_fit_score(600) == 5.0
    assert _length_fit_score(899) == 5.0
    assert _length_fit_score(900) == 6.5
    assert _length_fit_score(1199) == 6.5
    assert _length_fit_score(1200) == 8.0
    assert _length_fit_score(1499) == 8.0
    assert _length_fit_score(1500) == 10.0
    assert _length_fit_score(2200) == 10.0
    assert _length_fit_score(2201) == 8.0
    assert _length_fit_score(2600) == 8.0
    assert _length_fit_score(2601) == 6.0
    assert _length_fit_score(3000) == 6.0
    assert _length_fit_score(3001) == 4.0


def test_apply_length_fit_overwrites_judge_score_regardless_of_input():
    # The judge scored short drafts 8-10/10 in live testing despite the
    # target being spelled out in its rubric -- this deterministic override
    # exists specifically so that can never happen again.
    scores = {"length_fit": {"score": 9.5, "reason": "judge said it's fine"}}
    draft_text = "x" * 400  # well under the 1500-2200 target
    _apply_length_fit(scores, draft_text, brief="", transcript=[])
    assert scores["length_fit"]["score"] == 3.0
    assert "judge said it's fine" not in scores["length_fit"]["reason"]


def test_apply_length_fit_in_target_range_reason_mentions_range():
    scores = {"length_fit": {"score": 0, "reason": ""}}
    _apply_length_fit(scores, "x" * 1800, brief="", transcript=[])
    assert scores["length_fit"]["score"] == 10.0
    assert "1500-2200" in scores["length_fit"]["reason"]


def test_apply_length_fit_short_with_thin_material_blames_material():
    scores = {"length_fit": {"score": 0, "reason": ""}}
    _apply_length_fit(scores, "x" * 400, brief="short brief", transcript=[])
    assert "invented facts" in scores["length_fit"]["reason"]


def test_apply_length_fit_short_with_rich_material_does_not_blame_material():
    scores = {"length_fit": {"score": 0, "reason": ""}}
    rich_brief = "x" * 500  # >= _LENGTH_RICHNESS_THRESHOLD (300)
    _apply_length_fit(scores, "y" * 400, brief=rich_brief, transcript=[])
    assert "invented facts" not in scores["length_fit"]["reason"]
    assert "acceptable" in scores["length_fit"]["reason"]


def test_apply_length_fit_over_target_mentions_truncation():
    scores = {"length_fit": {"score": 0, "reason": ""}}
    _apply_length_fit(scores, "x" * 2400, brief="", transcript=[])
    assert scores["length_fit"]["score"] == 8.0
    assert "truncates" in scores["length_fit"]["reason"]
