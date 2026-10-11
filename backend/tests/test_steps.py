"""Step engine: one queue task per step; the app decides every next step."""
import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.taxonomy import GATE_PILLARS, OPTIMIZATION_PILLARS
from app.config import settings
from app.db.database import Base
from app.db.models import Post, PostDraft
from app.services import steps
from app.services.steps import Next, Wait, decide_next

# ---------------------------------------------------------------- decide_next


def _failing(pillar, fix_type="rewrite"):
    return {"pillar": pillar, "reason": "weak", "fix_type": fix_type}


def test_category_then_clarify():
    assert decide_next("category", {}, {}) == Next("clarify", {})


def test_clarify_question_waits_for_user_and_done_starts_draft():
    assert decide_next("clarify", {"done": False}, {}) == Wait({})
    assert decide_next("clarify", {"done": True}, {}) == Next(
        "draft", {"automatic": True, "attempt": 1})


def test_draft_and_rewrite_go_to_judge_keeping_context():
    ctx = {"automatic": True, "attempt": 2}
    assert decide_next("draft", {}, ctx) == Next("judge", ctx)
    assert decide_next("rewrite", {}, ctx) == Next("judge", ctx)


def _judge(failing=(), thin=False):
    return {"failing": list(failing), "thin_material": thin, "material": 120 if thin else 900}


def test_judge_all_pass_finishes_in_drafting():
    assert decide_next("judge", _judge(), {"automatic": True, "attempt": 1}) == Wait(
        {"status": "drafting", "escalation_reason": None})


def test_judge_thin_material_escalates_before_anything_else():
    nxt = decide_next("judge", _judge([_failing("hook")], thin=True),
                      {"automatic": True, "attempt": 1})
    assert nxt.step == "escalation"
    assert nxt.ctx["failing"][0]["pillar"] == "material_sufficiency"


def test_judge_non_rewrite_failure_escalates():
    bad = _failing("factual_integrity", "needs_material")
    nxt = decide_next("judge", _judge([bad, _failing("hook")]), {"automatic": True, "attempt": 1})
    assert nxt == Next("escalation", {"failing": [bad]})


def test_judge_rewrite_fixable_rewrites_with_critique_until_cap():
    nxt = decide_next("judge", _judge([_failing("hook")]), {"automatic": True, "attempt": 1})
    assert nxt.step == "rewrite"
    assert nxt.ctx["automatic"] is True and nxt.ctx["attempt"] == 2
    assert "hook" in nxt.ctx["instruction"]


def test_judge_gives_best_effort_after_max_attempts():
    out = decide_next("judge", _judge([_failing("hook")]),
                      {"automatic": True, "attempt": settings.max_recalibration_passes})
    assert isinstance(out, Wait) and out.updates["status"] == "drafting"
    assert "couldn't fully clear" in out.updates["escalation_reason"]


def test_manual_rescore_never_loops_or_escalates():
    bad = _failing("factual_integrity", "needs_material")
    assert decide_next("judge", _judge([bad], thin=True), {"automatic": False}) == Wait({})


def test_escalation_scene_and_image_end_in_their_stages():
    assert decide_next("escalation", {}, {}) == Wait({"status": "needs_input"})
    assert decide_next("scene", {}, {}) == Wait({"status": "locked"})
    assert decide_next("image", {}, {}) == Wait({"status": "image_ready"})


# ---------------------------------------------------------------- engine with a fake queue


class FakeQueue:
    """Records submitted tasks; tests set each task's queue status/result."""

    def __init__(self):
        self.tasks = {}

    def submitted(self, task_type=None):
        return [t for t in self.tasks.values() if task_type in (None, t["task_type"])]

    def latest(self):
        return list(self.tasks.values())[-1]

    def finish(self, content=None, error=None, result=None):
        task = self.latest()
        if error:
            task.update(status="failed", error=error)
        else:
            task.update(status="done", result=result or {"content": content})

    async def post(self, url, json, timeout):
        task_id = f"t{len(self.tasks) + 1}"
        self.tasks[task_id] = {"id": task_id, "task_type": json["task_type"],
                               "payload": json["payload"], "status": "queued"}

        class R:
            def raise_for_status(self):
                pass

            def json(self_inner):
                return {"id": task_id, "status": "queued"}
        return R()

    async def get(self, url, timeout):
        if "/api/artifacts/" in url:
            data = {"url": "https://storage/img.png"}
        else:
            data = dict(self.tasks[url.rsplit("/", 1)[1]])

        class R:
            def raise_for_status(self):
                pass

            def json(self_inner):
                return data
        return R()


def _scores_json(score):
    return json.dumps({p: {"score": score, "reason": "r"} for p in GATE_PILLARS + OPTIMIZATION_PILLARS})


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _run(coro):
    return asyncio.run(coro)


def _active(post):
    return json.loads(post.active_step)["name"] if post.active_step else None


LONG_BRIEF = "We cut the nightly pipeline from four hours to fifty minutes. " * 8


def test_create_flow_runs_one_task_per_step_and_waits_for_the_user(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None))
    assert _active(post) == "category" and post.status == "clarifying"
    assert len(q.submitted("text_generation")) == 1  # acknowledged after ONE submission

    q.finish('{"category": "lessons_learned"}')
    post = _run(steps.advance(db, q, post))
    assert post.category == "lessons_learned" and _active(post) == "clarify"

    q.finish('{"done": false, "question": "Which team was it?"}')
    post = _run(steps.advance(db, q, post))
    assert _active(post) is None and post.status == "clarifying"
    assert json.loads(post.clarify_transcript)[-1] == {"question": "Which team was it?",
                                                       "answer": None}

    post = _run(steps.start_clarify_answer(db, q, post.id, "Analytics, six engineers."))
    q.finish('{"done": true}')
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "draft"

    draft = "A grounded post about ownership and the pipeline we fixed. " * 30  # ~1800 chars
    q.finish(draft)
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "judge" and post.post_text == draft.strip()
    assert db.query(PostDraft).count() == 1

    q.finish(_scores_json(9.5))
    post = _run(steps.advance(db, q, post))
    assert _active(post) is None and post.status == "drafting"
    assert len(q.submitted()) == 5  # category, clarify, clarify, draft, judge -- nothing extra


def test_status_check_while_running_changes_nothing(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None))
    q.latest()["status"] = "claimed"
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "category" and len(q.submitted()) == 1


def test_failed_step_records_error_and_retry_resubmits_same_step(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None))
    q.finish(error="text_unavailable: Ollama not reachable")
    post = _run(steps.advance(db, q, post))
    assert _active(post) is None and "Ollama not reachable" in post.step_error

    post = _run(steps.retry_step(db, q, post.id))
    assert _active(post) == "category" and post.step_error is None
    assert len(q.submitted()) == 2


def test_compute_action_on_a_busy_post_is_rejected(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None))
    with pytest.raises(steps.StepError, match="busy"):
        _run(steps.retry_step(db, q, post.id))


def test_lock_and_image_steps(db):
    q = FakeQueue()
    post = Post(character_id="gtee_dev", brief="b", status="drafting", post_text="A post.",
                clarify_transcript="[]")
    db.add(post)
    db.commit()
    post = _run(steps.start_lock(db, q, post.id))
    q.finish(json.dumps({"action": "waving", "setting_name": None, "setting_detail": None,
                         "angle": "front view", "mood": "happy"}))
    post = _run(steps.advance(db, q, post))
    assert post.status == "locked" and "waving" in post.scene_instruction and post.seed

    post = _run(steps.start_image(db, q, post.id, "lightning"))
    assert post.status == "image_queued" and _active(post) == "image"
    assert q.latest()["task_type"] == "image_generation"
    assert q.latest()["payload"]["profile"] == "lightning"
    q.finish(result={"image_artifact_id": "a1"})
    post = _run(steps.advance(db, q, post))
    assert post.status == "image_ready" and post.final_image_path == "https://storage/img.png"


def test_failed_image_keeps_image_failure_fields(db):
    q = FakeQueue()
    post = Post(character_id="gtee_dev", brief="b", status="locked", post_text="p",
                scene_instruction="waving", seed=3, clarify_transcript="[]")
    db.add(post)
    db.commit()
    post = _run(steps.start_image(db, q, post.id, "full"))
    q.finish(error="insufficient_memory: full quality needs 14 GB")
    post = _run(steps.advance(db, q, post))
    assert post.status == "image_failed"
    assert post.image_job_error.startswith("insufficient_memory:")


def test_two_pollers_never_submit_the_next_step_twice(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    q = FakeQueue()
    s1 = Session()
    post = _run(steps.start_create(s1, q, LONG_BRIEF, None))
    s2 = Session()
    stale = s2.get(Post, post.id)  # second tab loaded the same state
    q.finish('{"category": "lessons_learned"}')

    _run(steps.advance(s1, q, s1.get(Post, post.id)))
    _run(steps.advance(s2, q, stale))

    assert len(q.submitted()) == 2  # category + exactly ONE clarify
    s1.close()
    s2.close()
