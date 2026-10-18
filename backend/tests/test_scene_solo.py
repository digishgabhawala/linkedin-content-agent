"""The mascot must be the only figure in every render. scene_agent output that
puts other people (or a second copy) into the scene is rewritten
deterministically -- no automatic re-ask, since compute is one task per step.
"""
import json

import pytest

from app.agents.scene_agent import SYSTEM_PROMPT, parse_scene
from app.agents.scene_solo import make_solo, people_terms_in
from app.config import settings


def _scene(**overrides) -> str:
    scene = {"action": "sketching in a notebook, pen mid-stroke",
             "setting_name": None, "setting_detail": "on a wooden tabletop",
             "angle": "side view", "mood": "focused"}
    scene.update(overrides)
    return json.dumps(scene)


# The live case that rendered two mascots (post dd3415df..., lightning).
def test_live_collaborative_scene_loses_the_people_wording():
    scene = parse_scene(_scene(
        action="weaving a tangle of threads between multiple points, some connected, "
               "others loose",
        mood="determined, collaborative"))
    assert scene["mood"] == "determined"
    # "others" refers to threads here -- not a person, kept.
    assert scene["action"] == ("weaving a tangle of threads between multiple points, "
                               "some connected, others loose")


@pytest.mark.parametrize("action, expected", [
    ("pairing with a colleague at a shared monitor, pointing at a diagram",
     "pairing at a shared monitor, pointing at a diagram"),
    ("brainstorming with teammates around a whiteboard covered in sticky notes",
     "brainstorming around a whiteboard covered in sticky notes"),
    ("sliding a puzzle piece into place alongside two coworkers",
     "sliding a puzzle piece into place"),
    ("building a bridge of blocks together, one block mid-placement",
     "building a bridge of blocks, one block mid-placement"),
    ("connecting cables between laptops, a team of engineers watching",
     "connecting cables between laptops"),
    ("shaking hands with a partner over a finished blueprint",
     "giving a thumbs-up over a finished blueprint"),
    ("leading a meeting, gesturing at a chart",
     "gesturing at a chart"),
])
def test_people_phrases_are_rewritten(action, expected):
    assert parse_scene(_scene(action=action))["action"] == expected


def test_duplicates_and_reflections_are_removed():
    scene = parse_scene(_scene(
        action="looking into a mirror, the reflection frowning back",
        setting_detail="against a plain wall, a second copy of the character in the corner"))
    assert "mirror" not in scene["action"] and "reflection" not in scene["action"]
    assert scene["action"]  # never empty
    assert scene["setting_detail"] == "against a plain wall"


def test_people_in_the_setting_are_dropped_clause_by_clause():
    scene = parse_scene(_scene(
        setting_name="office",
        setting_detail="a long desk with two monitors, colleagues chatting in the "
                       "background, a wall clock with a blank face"))
    # "two monitors" is not people -- counting words only matter for figures.
    assert scene["setting_detail"] == "a long desk with two monitors, a wall clock with a blank face"


def test_a_mood_that_was_only_people_falls_back_to_a_neutral_one():
    assert parse_scene(_scene(mood="collaborative, team spirit"))["mood"] == "neutral"


def test_counting_words_only_matter_when_they_count_people():
    for ok in ("balancing two stacks of books", "toppling another domino",
               "holding both ends of a rope", "two monitors on a desk"):
        assert people_terms_in(ok) == []
    for bad in ("two people at a desk", "another engineer waving",
                "both of them laughing", "high-fiving each other"):
        assert people_terms_in(bad), bad


def test_solo_scene_is_untouched():
    raw = _scene(action="resetting toppled dominoes one at a time, focused",
                 setting_detail="on a wooden tabletop, soft lamp light",
                 mood="focused, evening, dim desk lamp")
    assert parse_scene(raw) == json.loads(raw)


def test_people_words_are_configurable(monkeypatch):
    monkeypatch.setattr(settings, "scene_people_terms", ["robot"])
    assert make_solo("talking to a robot, waving") == "talking, waving"
    assert make_solo("talking with colleagues, waving") == "talking with colleagues, waving"


def test_the_prompt_tells_the_model_to_show_collaboration_without_people():
    lowered = SYSTEM_PROMPT.lower()
    assert "the only figure" in lowered
    for idea in ("sticky notes", "connected nodes", "empty chairs", "video-call window"):
        assert idea in lowered
    assert "never other people" in lowered


def test_every_worked_example_scene_is_solo():
    """The examples are what the model copies -- none may put a second figure in."""
    from pathlib import Path
    text = Path(settings.scene_examples_path).read_text()
    scenes = [line.split("SCENE: ", 1)[1] for line in text.splitlines()
              if line.startswith("SCENE: ")]
    assert len(scenes) >= 18
    for raw in scenes:
        scene = json.loads(raw)
        for key in ("action", "setting_detail", "angle", "mood"):
            assert people_terms_in(scene[key]) == [], (key, scene[key])
