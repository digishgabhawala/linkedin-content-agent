import pytest

from app.agents.taxonomy import CATEGORIES, PILLAR_WEIGHTS, weighted_score


@pytest.mark.parametrize("category", CATEGORIES.keys())
def test_pillar_weights_sum_to_one_per_category(category):
    total = sum(PILLAR_WEIGHTS[category].values())
    assert total == pytest.approx(1.0, abs=1e-6)


def test_weighted_score_all_tens_is_ten():
    scores = {p: 10.0 for p in PILLAR_WEIGHTS["technical_deep_dive"]}
    assert weighted_score("technical_deep_dive", scores) == pytest.approx(10.0)


def test_weighted_score_all_zeros_is_zero():
    scores = {p: 0.0 for p in PILLAR_WEIGHTS["milestone"]}
    assert weighted_score("milestone", scores) == pytest.approx(0.0)


def test_weighted_score_unknown_category_falls_back_to_technical_deep_dive():
    scores = {p: 10.0 for p in PILLAR_WEIGHTS["technical_deep_dive"]}
    assert weighted_score("not_a_real_category", scores) == pytest.approx(10.0)


def test_weighted_score_missing_pillar_treated_as_zero():
    weights = PILLAR_WEIGHTS["exploration"]
    scores = {p: 10.0 for p in weights if p != "hook"}  # omit one pillar entirely
    score = weighted_score("exploration", scores)
    assert score == pytest.approx(10.0 * (1 - weights["hook"]))
