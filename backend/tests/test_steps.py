"""Step engine: one queue task per step; the app decides every next step."""
import asyncio
import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.taxonomy import GATE_PILLARS, OPTIMIZATION_PILLARS
from app.auth import LOCAL_USER_ID
from app.config import settings
from app.db.database import Base
from app.db.models import Character, Post, PostDraft
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
        if "/artifacts/" in url:
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
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
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
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    q.latest()["status"] = "claimed"
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "category" and len(q.submitted()) == 1


def test_failed_step_records_error_and_retry_resubmits_same_step(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    q.finish(error="text_unavailable: Ollama not reachable")
    post = _run(steps.advance(db, q, post))
    assert _active(post) is None and "Ollama not reachable" in post.step_error

    post = _run(steps.retry_step(db, q, post.id))
    assert _active(post) == "category" and post.step_error is None
    assert len(q.submitted()) == 2


def test_compute_action_on_a_busy_post_is_rejected(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    with pytest.raises(steps.StepError, match="busy"):
        _run(steps.retry_step(db, q, post.id))


def test_lock_and_image_steps(db):
    q = FakeQueue()
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="drafting", post_text="A post.",
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
    assert post.image_profile == "lightning"  # remembered for Retry
    assert q.latest()["task_type"] == "image_generation"
    assert q.latest()["payload"]["profile"] == "lightning"
    q.latest().update(status="claimed", claimed_by="mac-worker", progress_stage="rendering",
                      progress_message="ComfyUI is generating the image")
    post = _run(steps.advance(db, q, post))  # live progress for the image card
    assert post.image_queue_status == "claimed" and post.image_worker_id == "mac-worker"
    assert post.image_progress_stage == "rendering"
    q.finish(result={"image_artifact_id": "a1"})
    post = _run(steps.advance(db, q, post))
    assert post.status == "image_ready" and post.final_image_path == "https://storage/img.png"


def test_image_task_carries_remote_locked_hero_snapshot(db):
    q = FakeQueue()
    card = {"character_id": "remote_dev", "trigger_token": "remote_dev",
            "display_name": "Remote Dev"}
    db.add(Character(owner_id=LOCAL_USER_ID, character_id="remote_dev", card_json=json.dumps(card),
                     hero_asset_id="sha256:abc", hero_version=3,
                     hero_image_url="https://storage.example/hero.png"))
    post = Post(owner_id=LOCAL_USER_ID, character_id="remote_dev", brief="b", status="locked", post_text="p",
                scene_instruction="waving", seed=3, clarify_transcript="[]")
    db.add(post)
    db.commit()

    _run(steps.start_image(db, q, post.id, "full"))

    payload = q.latest()["payload"]
    assert payload["hero_image_url"] == "https://storage.example/hero.png"
    assert payload["hero_asset_id"] == "sha256:abc"
    assert payload["hero_version"] == 3
    assert payload["character_card"] == card


def test_failed_image_keeps_image_failure_fields(db):
    q = FakeQueue()
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="locked", post_text="p",
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
    post = _run(steps.start_create(s1, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    s2 = Session()
    stale = s2.get(Post, post.id)  # second tab loaded the same state
    q.finish('{"category": "lessons_learned"}')

    _run(steps.advance(s1, q, s1.get(Post, post.id)))
    _run(steps.advance(s2, q, stale))

    assert len(q.submitted()) == 2  # category + exactly ONE clarify
    s1.close()
    s2.close()


def test_image_submitted_before_the_step_engine_still_completes(db):
    q = FakeQueue()
    _run(q.post("/api/tasks", {"task_type": "image_generation", "payload": {}}, 30))
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="image_queued", post_text="p",
                scene_instruction="waving", seed=3, clarify_transcript="[]",
                image_task_id="t1")  # pre-3a: no active_step recorded
    db.add(post)
    db.commit()
    q.finish(result={"image_artifact_id": "a1"})
    post = _run(steps.advance(db, q, post))
    assert post.status == "image_ready" and post.final_image_path == "https://storage/img.png"


def test_after_a_hand_off_the_new_step_does_not_show_the_old_tasks_status(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    q.finish('{"category": "lessons_learned"}')
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "clarify"
    assert getattr(post, "active_task", None) is None  # not the finished category task


# ---------------------------------------------------------------- review fixes


class NotFoundQueue(FakeQueue):
    """The queue purged the task (e.g. 2h text-task retention)."""

    async def get(self, url, timeout):
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("404", request=request,
                                    response=httpx.Response(404, request=request))


def test_task_gone_from_queue_becomes_a_retryable_failure_not_busy_forever(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    gone = NotFoundQueue()
    gone.tasks = q.tasks
    post = _run(steps.advance(db, gone, post))
    assert post.active_step is None and post.step_error.startswith("lost:")
    post = _run(steps.retry_step(db, q, post.id))
    assert _active(post) == "category"


def test_claim_is_committed_before_any_network_wait(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'claim.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seen = {}

    class Watching(FakeQueue):
        async def get(self, url, timeout):
            if "/artifacts/" in url:  # a network await inside apply()
                with Session() as other:
                    seen["active_step_in_db"] = other.get(Post, pid).active_step
            return await super().get(url, timeout)

    q = Watching()
    s = Session()
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="locked", post_text="p",
                scene_instruction="waving", seed=3, clarify_transcript="[]")
    s.add(post)
    s.commit()
    pid = post.id
    post = _run(steps.start_image(s, q, pid, "lightning"))
    q.finish(result={"image_artifact_id": "a1"})
    post = _run(steps.advance(s, q, post))
    claimed = json.loads(seen["active_step_in_db"])  # committed before the network wait...
    assert claimed["name"] == "image" and claimed.get("claimed_at")  # ...and still busy
    assert post.status == "image_ready"
    s.close()


class BadArtifactQueue(FakeQueue):
    async def get(self, url, timeout):
        if "/artifacts/" in url:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("500", request=request,
                                        response=httpx.Response(500, request=request))
        return await super().get(url, timeout)


def test_error_while_applying_a_result_is_recorded_once_not_repeated_every_poll(db):
    q = BadArtifactQueue()
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="locked", post_text="p",
                scene_instruction="waving", seed=3, clarify_transcript="[]")
    db.add(post)
    db.commit()
    post = _run(steps.start_image(db, q, post.id, "full"))
    q.finish(result={"image_artifact_id": "a1"})
    post = _run(steps.advance(db, q, post))
    assert post.active_step is None and post.step_error and steps.can_retry(post)
    post = _run(steps.advance(db, q, post))  # next poll: nothing to redo, no exception
    assert post.active_step is None


def test_non_object_json_from_the_model_fails_safe():
    from app.agents.category_agent import parse_category
    from app.agents.draft_agent import parse_clarify
    from app.agents.judge_agent import parse_judge
    from app.agents.scene_agent import parse_scene
    assert parse_category("[]") == "technical_deep_dive"
    assert parse_clarify('"x"') == {"done": True, "question": None}
    assert all(v["score"] == 0.0 for v in parse_judge("[1, 2]").values())
    assert parse_scene("[]")["setting_name"] is None


def test_clarify_turn_cap_forces_draft(db):
    q = FakeQueue()
    turns = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(settings.clarify_max_turns)]
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief=LONG_BRIEF, status="clarifying",
                category="lessons_learned", clarify_transcript=json.dumps(turns))
    db.add(post)
    db.commit()
    post = _run(steps._begin(db, q, post, "clarify", {}))
    q.finish('{"done": false, "question": "one more?"}')  # model wants more; cap says no
    post = _run(steps.advance(db, q, post))
    assert _active(post) == "draft"


def test_automatic_loop_rewrites_with_critique_then_escalates(db):
    q = FakeQueue()
    draft = "A grounded post about ownership and the pipeline we fixed. " * 30
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief=LONG_BRIEF, status="clarifying",
                category="lessons_learned", clarify_transcript="[]", post_text=None)
    db.add(post)
    db.commit()
    post = _run(steps._begin(db, q, post, "draft", {"automatic": True, "attempt": 1}))
    q.finish(draft)
    post = _run(steps.advance(db, q, post))                 # -> judge
    weak_hook = json.loads(_scores_json(9.5))
    weak_hook["hook"] = {"score": 3.0, "reason": "generic opener"}
    q.finish(json.dumps(weak_hook))
    post = _run(steps.advance(db, q, post))                 # -> rewrite (attempt 2)
    assert _active(post) == "rewrite" and post.recalibration_count == 1
    assert "hook" in q.latest()["payload"]["messages"][-1]["content"]
    q.finish(draft)
    post = _run(steps.advance(db, q, post))                 # -> judge
    rewrite = db.query(PostDraft).order_by(PostDraft.version.desc()).first()
    assert rewrite.generated_by == "recalibration" and "hook" in rewrite.user_instruction
    needs = json.loads(_scores_json(9.5))
    needs["factual_integrity"] = {"score": 2.0, "reason": "numbers missing"}
    q.finish(json.dumps(needs))
    post = _run(steps.advance(db, q, post))                 # -> escalation
    assert _active(post) == "escalation" and post.recalibration_count == 2
    q.finish("What was the before/after number?")
    post = _run(steps.advance(db, q, post))
    assert post.status == "needs_input"
    assert post.escalation_reason == "What was the before/after number?"


def test_manual_regenerate_rescores_without_changing_status_or_count(db):
    q = FakeQueue()
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief=LONG_BRIEF, status="drafting", post_text="old",
                category="lessons_learned", clarify_transcript="[]", recalibration_count=3)
    db.add(post)
    db.commit()
    post = _run(steps.start_regenerate(db, q, post.id, "shorter please"))
    q.finish("new text " * 200)
    post = _run(steps.advance(db, q, post))
    q.finish(_scores_json(1.0))  # terrible scores: still no loop, no escalation
    post = _run(steps.advance(db, q, post))
    assert post.active_step is None and post.status == "drafting"
    assert post.recalibration_count == 3


def test_image_retry_and_reroll_get_a_fresh_seed(db, monkeypatch):
    q = FakeQueue()
    seeds = iter([111, 222])
    monkeypatch.setattr(steps.random, "randint", lambda a, b: next(seeds))
    post = Post(owner_id=LOCAL_USER_ID, character_id="gtee_dev", brief="b", status="locked", post_text="p",
                scene_instruction="waving", seed=7, clarify_transcript="[]")
    db.add(post)
    db.commit()
    post = _run(steps.start_image(db, q, post.id, "full"))
    assert q.latest()["payload"]["seed"] == 7  # first render keeps the locked seed
    q.finish(error="corrupt_output: near-uniform image")
    post = _run(steps.advance(db, q, post))
    post = _run(steps.retry_step(db, q, post.id))  # retry of a failed image
    assert q.latest()["payload"]["seed"] == 111 and post.status == "image_queued"



def test_post_stays_busy_while_another_request_is_handing_off(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'handoff.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    q = FakeQueue()
    s = Session()
    post = _run(steps.start_create(s, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    q.finish('{"category": "lessons_learned"}')
    # simulate another request that claimed the transition and is mid-hand-off
    marker = json.dumps({**json.loads(post.active_step), "claimed_at": steps._now_iso()})
    s.execute(steps.update(Post).where(Post.id == post.id).values(active_step=marker))
    s.commit()
    other = Session()
    view = _run(steps.advance(other, q, other.get(Post, post.id)))
    assert view.active_step == marker            # still busy, not idle
    assert len(q.submitted()) == 1               # and it did not submit anything itself
    s.close()
    other.close()


def test_stale_claim_from_a_crashed_request_becomes_retryable(db):
    q = FakeQueue()
    post = _run(steps.start_create(db, q, LONG_BRIEF, None, owner_id=LOCAL_USER_ID))
    stale = json.loads(post.active_step) | {"claimed_at": "2020-01-01T00:00:00+00:00"}
    post.active_step = json.dumps(stale)
    db.commit()
    post = _run(steps.advance(db, q, post))
    assert post.active_step is None and post.step_error.startswith("interrupted:")
    assert steps.can_retry(post)
