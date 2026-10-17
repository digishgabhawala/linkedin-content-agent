"""steps.py -- the step engine (phase 3a).

Core rule (system-wide): compute goes through the task-queue as ONE task per
step; a request only submits a step and returns. The app -- as the caller --
observes each finished step and decides the next one itself, even when step
B always follows step A today (keeps flows changeable, e.g. pausing for the
UI between steps).

  build(step)            -> the task to submit (pure, no I/O)
  apply(step, result)    -> records the result on the post (the only writer)
  decide_next(step, ...) -> Next(step, ctx) | Wait(post updates)  (pure)
  advance(post)          -> on each status check: if the active task finished,
                            claim the transition (compare-and-set), apply,
                            decide, submit the next step

Known limitation: advancing happens only when someone checks the post's
status (the UI polls while open). A finished step's successor is not
submitted until the post is viewed again.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..agents.category_agent import build_category_request, parse_category
from ..agents.content_sources import load_user_profile
from ..agents.draft_agent import (
    build_clarify_request,
    build_draft_request,
    build_escalation_request,
    build_rewrite_request,
    parse_clarify,
    parse_draft,
    parse_escalation,
)
from ..agents.judge_agent import build_judge_request, parse_judge
from ..agents.scene_agent import build_scene_request, parse_scene
from ..agents.taxonomy import (
    FIX_TYPE,
    GATE_PILLARS,
    GATE_THRESHOLD,
    OPTIMIZATION_PILLARS,
    RECALIBRATION_THRESHOLD,
    weighted_score,
)
from ..config import settings
from ..db.models import Post, PostDraft
from . import llm_client
from .post_service import (
    _MIN_MATERIAL_CHARS,
    PostServiceError,
    _answered_turns,
    _apply_length_fit,
    _assemble_scene_text,
    _load_transcript,
    _material_chars,
    _resolve_scene_asset,
    _save_transcript,
    expand_scene_refs,
    get_post,
)


class StepError(PostServiceError):
    """A step action that isn't allowed in the post's current state."""


class BusyError(StepError):
    """The post already has a step in flight."""


@dataclass(frozen=True)
class Next:
    step: str
    ctx: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Wait:
    """No further step: wait for the user. `updates` are post fields to set."""
    updates: dict = field(default_factory=dict)


# ------------------------------------------------------------------ decisions


def decide_next(step: str, outcome: dict, ctx: dict) -> Next | Wait:
    """Every 'what happens after this step' decision, in one place."""
    if step == "category":
        return Next("clarify", {})
    if step == "clarify":
        return Next("draft", {"automatic": True, "attempt": 1}) if outcome["done"] else Wait({})
    if step in ("draft", "rewrite"):
        return Next("judge", ctx)
    if step == "judge":
        return _decide_after_judge(outcome, ctx)
    if step == "escalation":
        return Wait({"status": "needs_input"})
    if step == "scene":
        return Wait({"status": "locked"})
    if step == "image":
        return Wait({"status": "image_ready"})
    raise ValueError(f"unknown step {step!r}")


def _decide_after_judge(outcome: dict, ctx: dict) -> Next | Wait:
    if not ctx.get("automatic"):
        # Manual redraft/regenerate: re-score only so the shown scores match
        # the text on screen -- no automatic loop, no escalation.
        return Wait({})
    failing = outcome["failing"]
    attempt = ctx.get("attempt", 1)
    # Thin-material gate first: no rewrite can fix missing substance and the
    # writer may not invent -- ask the human for material.
    if outcome["thin_material"]:
        return Next("escalation", {"failing": [{
            "pillar": "material_sufficiency", "fix_type": "needs_material",
            "reason": (f"the brief plus clarification total only ~{outcome['material']} "
                       "characters of real material -- not enough to build a strong post "
                       "without inventing facts. A short honest draft exists as a starting "
                       "point, but it needs real additional detail (mechanism, numbers, what "
                       "was tried, why it mattered) to become a good post.")}]})
    needs_escalation = [f for f in failing if f["fix_type"] != "rewrite"]
    if needs_escalation:
        return Next("escalation", {"failing": needs_escalation})
    if not failing:
        return Wait({"status": "drafting", "escalation_reason": None})
    if attempt >= settings.max_recalibration_passes:
        reasons = "; ".join(f"{f['pillar']} ({f.get('score', '?')}/10): {f['reason']}"
                            for f in failing)
        return Wait({"status": "drafting", "escalation_reason": (
            f"Automatic recalibration ({attempt} passes) couldn't fully clear every pillar. "
            f"Still short on: {reasons}. You can accept this draft as-is or keep refining "
            "it manually.")})
    critique = "Improve the following, based on specific critique:\n" + "\n".join(
        f"- {f['pillar']} ({f.get('score', '?')}/10): {f['reason']}" for f in failing)
    return Next("rewrite", {"automatic": True, "attempt": attempt + 1, "instruction": critique})


# ------------------------------------------------------------------ build / apply


def _transcript(post: Post) -> list[dict]:
    return _answered_turns(_load_transcript(post))


def _personality(post: Post) -> str | None:
    return post.character.personality if post.character else None


def _remote_character_payload(post: Post) -> dict:
    """Remote locked-hero snapshot for a stateless image worker.

    Legacy characters without a synced card deliberately return no extra
    fields, preserving the worker's local workspace fallback.
    """
    character = post.character
    if not character or not character.hero_image_url or not character.card_json:
        return {}
    try:
        card = json.loads(character.card_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(card, dict):
        return {}
    return {
        "hero_image_url": character.hero_image_url,
        "hero_asset_id": character.hero_asset_id,
        "hero_version": character.hero_version,
        "character_card": card,
    }


def build(db: Session, post: Post, step: str, ctx: dict):
    """-> ("text", LLMRequest) or ("image", payload). Pure apart from DB reads."""
    if step == "category":
        return "text", build_category_request(post.brief)
    if step == "clarify":
        return "text", build_clarify_request(post.brief, _transcript(post), post.category)
    if step == "draft":
        return "text", build_draft_request(post.brief, _transcript(post), _personality(post),
                                           post.category)
    if step == "rewrite":
        return "text", build_rewrite_request(post.post_text, ctx["instruction"],
                                             _personality(post), post.category)
    if step == "judge":
        return "text", build_judge_request(
            post.post_text, post.brief, _transcript(post), post.category,
            _personality(post), load_user_profile())
    if step == "escalation":
        return "text", build_escalation_request(post.brief, post.category, ctx["failing"])
    if step == "scene":
        return "text", build_scene_request(post.post_text)
    if step == "image":
        # Scene "@name" references expand at the last moment using the exact
        # immutable revision pinned by this post.
        return "image", {"character_id": post.character_id,
                         "task": expand_scene_refs(
                             db, post.scene_instruction,
                             post.scene_asset_name, post.scene_asset_version_id,
                             owner_id=post.owner_id),
                         "seed": post.seed, "profile": ctx.get("profile", "full"),
                         **_remote_character_payload(post)}
    raise ValueError(f"unknown step {step!r}")


async def apply(db: Session, client, post: Post, step: str, result: dict, ctx: dict) -> dict:
    """Record a finished step's result on the post. Returns the outcome
    decide_next needs."""
    content = (result or {}).get("content", "")
    if step == "category":
        post.category = parse_category(content)
        return {}
    if step == "clarify":
        answered = _transcript(post)
        parsed = parse_clarify(content)
        # Cap: a thin brief stays thin rather than looping on questions.
        done = parsed["done"] or len(answered) >= settings.clarify_max_turns
        if done:
            _save_transcript(post, answered)
        else:
            _save_transcript(post, answered + [{"question": parsed["question"], "answer": None}])
        return {"done": done}
    if step in ("draft", "rewrite"):
        text = parse_draft(content)
        version = post.draft_version + 1
        generated_by = "draft" if step == "draft" else (
            "recalibration" if ctx.get("automatic") else "regenerate")
        db.add(PostDraft(post_id=post.id, version=version, post_text=text,
                         generated_by=generated_by,
                         user_instruction=ctx.get("instruction") if step == "rewrite" else None))
        post.post_text = text
        post.draft_version = version
        return {}
    if step == "judge":
        transcript = _transcript(post)
        scores = parse_judge(content)
        _apply_length_fit(scores, post.post_text, post.brief, transcript)
        post.gate_scores = json.dumps({p: scores[p] for p in GATE_PILLARS})
        pillar_scores = {p: scores[p] for p in OPTIMIZATION_PILLARS}
        post.pillar_scores = json.dumps(pillar_scores)
        post.weighted_score = weighted_score(
            post.category, {p: s["score"] for p, s in pillar_scores.items()})
        if ctx.get("automatic"):
            post.recalibration_count = ctx.get("attempt", 1)
        failing = [{"pillar": p, "reason": scores[p]["reason"], "fix_type": FIX_TYPE[p],
                    "score": scores[p]["score"]}
                   for p in GATE_PILLARS if scores[p]["score"] < GATE_THRESHOLD]
        failing += [{"pillar": p, "reason": scores[p]["reason"], "fix_type": FIX_TYPE[p],
                     "score": scores[p]["score"]}
                    for p in OPTIMIZATION_PILLARS if scores[p]["score"] < RECALIBRATION_THRESHOLD]
        material = _material_chars(post.brief, transcript)
        return {"failing": failing, "thin_material": material < _MIN_MATERIAL_CHARS,
                "material": material}
    if step == "escalation":
        post.escalation_reason = parse_escalation(content)
        return {}
    if step == "scene":
        scene = parse_scene(content)
        setting_detail, asset_name, version_id = _resolve_scene_asset(
            db, scene, owner_id=post.owner_id)
        post.scene_instruction = _assemble_scene_text(scene, setting_detail)
        post.scene_asset_name = asset_name
        post.scene_asset_version_id = version_id
        post.seed = random.randint(1, 999_999)
        return {}
    if step == "image":
        artifact_id = result["image_artifact_id"]
        resp = await client.get(f"{settings.task_queue_api_url}/artifacts/{artifact_id}",
                                timeout=15)
        resp.raise_for_status()
        post.final_image_path = resp.json()["url"]
        post.image_job_error = None
        return {}
    raise ValueError(f"unknown step {step!r}")


# ------------------------------------------------------------------ engine


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def can_retry(post: Post) -> bool:
    return bool(post.step_error and not post.active_step and "_retry" in _ctx(post))


def active_step(post: Post) -> dict | None:
    return json.loads(post.active_step) if post.active_step else None


def _ctx(post: Post) -> dict:
    return json.loads(post.step_context) if post.step_context else {}


async def _start(db: Session, client, post: Post, step: str, ctx: dict) -> None:
    """Submit ONE step's task and mark it active (caller commits)."""
    kind, request = build(db, post, step, ctx)
    if kind == "text":
        task_id = await llm_client.submit_text(client, request)
    else:
        task_id = await llm_client.submit_image(client, request)
        post.image_task_id = task_id
    post.active_step = json.dumps({"name": step, "task_id": task_id, "started_at": _now_iso()})
    post.step_context = json.dumps(ctx)
    post.step_error = None


def _require_idle(post: Post) -> None:
    if post.active_step:
        raise BusyError(f"post {post.id} is busy with step "
                        f"{active_step(post)['name']!r} -- wait for it to finish")


async def _begin(db: Session, client, post: Post, step: str, ctx: dict) -> Post:
    _require_idle(post)
    try:
        await _start(db, client, post, step, ctx)
    except llm_client.TaskQueueUnavailable:
        db.rollback()  # nothing half-applied: the user's input wasn't accepted either
        raise
    db.commit()
    db.refresh(post)
    return post


def _attach_task_view(post: Post, step: str, task: dict) -> None:
    """Live queue view for the UI (not persisted)."""
    post.active_task = {k: task.get(k) for k in (
        "status", "claimed_by", "claimed_at", "progress_stage", "progress_message",
        "progress_updated_at", "lease_expires_at")}
    if step == "image":  # fields the image status card already understands
        post.image_queue_status = task.get("status")
        post.image_claimed_at = task.get("claimed_at")
        post.image_worker_id = task.get("claimed_by")
        post.image_lease_expires_at = task.get("lease_expires_at")
        post.image_progress_stage = task.get("progress_stage")
        post.image_progress_message = task.get("progress_message")
        post.image_progress_updated_at = task.get("progress_updated_at")


async def advance(db: Session, client, post: Post) -> Post:
    """Called on every status check: move the post forward if its active
    step's task has finished. Safe to call concurrently (compare-and-set)."""
    active = active_step(post)
    if active is None and post.status == "image_queued" and post.image_task_id:
        # Image submitted by the pre-step-engine code: adopt it as the active step.
        active = {"name": "image", "task_id": post.image_task_id, "started_at": None}
        post.active_step = json.dumps(active)
        post.step_context = json.dumps({"profile": post.image_profile or "full"})
        db.commit()
    if active is None:
        return post
    if active.get("claimed_at"):
        # Another request is mid-hand-off for this step: leave it alone, the
        # post stays busy. A claim that old means that request died -- make
        # the step retryable instead of busy forever.
        claimed_at = datetime.fromisoformat(active["claimed_at"])
        if datetime.now(timezone.utc) - claimed_at < STALE_CLAIM:
            return post
        if _claim(db, post, active):
            _record_failure(db, post, active["name"], _ctx(post),
                            "interrupted: the step's hand-off did not complete -- retry the step")
        return post
    try:
        task = await llm_client.get_task(client, active["task_id"])
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            return post  # transient: the next status check tries again
        # The queue no longer has this task (cleaned up after its retention,
        # e.g. nobody viewed the post for hours) -- fail it so it can be retried.
        task = {"status": "failed",
                "error": "lost: this step's task is no longer in the queue -- retry the step"}
    except httpx.HTTPError:
        return post  # transient: the next status check tries again
    _attach_task_view(post, active["name"], task)
    if task.get("status") not in ("done", "failed"):
        return post

    if not _claim(db, post, active):
        post.active_task = None
        return post
    post.active_task = None  # that task is finished; a next step starts fresh
    step, ctx = active["name"], _ctx(post)

    if task["status"] == "failed":
        if step == "image":
            post.status = "image_failed"
            post.image_job_error = task.get("error") or "image generation failed"
        _record_failure(db, post, step, ctx, task.get("error") or "step failed")
        return post

    # Apply the result and commit it, then decide and submit the next step.
    # Any error is recorded ONCE as a retryable step failure -- never left to
    # repeat on every poll.
    try:
        outcome = await apply(db, client, post, step, task.get("result") or {}, ctx)
        db.commit()
    except Exception as e:  # noqa: BLE001 -- surfaced to the user as step_error
        db.rollback()
        db.refresh(post)
        _record_failure(db, post, step, ctx, f"could not apply {step} result: {e}")
        return post
    decision = decide_next(step, outcome, ctx)
    if isinstance(decision, Next):
        try:
            await _start(db, client, post, decision.step, decision.ctx)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            db.refresh(post)
            _record_failure(db, post, decision.step, decision.ctx,
                            f"could not start {decision.step}: {e}")
            return post
    else:
        for name, value in decision.updates.items():
            setattr(post, name, value)
        post.active_step = None  # release the claim: the post now waits for the user
        post.step_context = None
        db.commit()
    db.refresh(post)
    return post


STALE_CLAIM = timedelta(minutes=5)


def _claim(db: Session, post: Post, active: dict) -> bool:
    """Compare-and-set the post's active step to a 'claimed' marker.

    Only the request whose UPDATE still sees the original value wins, so two
    pollers never both hand off. The marker keeps the post busy (plain
    actions stay refused) while the winner applies the result and submits
    the next step, and it is committed at once: no row lock is held across
    those network calls."""
    marker = json.dumps({**active, "claimed_at": _now_iso()})
    won = db.execute(update(Post)
                     .where(Post.id == post.id, Post.active_step == post.active_step)
                     .values(active_step=marker)
                     .execution_options(synchronize_session=False)).rowcount == 1
    if not won:
        db.rollback()
        db.refresh(post)
        return False
    db.commit()
    db.refresh(post)
    return True


def _record_failure(db: Session, post: Post, step: str, ctx: dict, error: str) -> None:
    """A step failed: keep what's needed to retry it, offer Retry step."""
    post.active_step = None
    post.step_error = error
    post.step_context = json.dumps({**ctx, "_retry": step})
    db.commit()
    db.refresh(post)


# ------------------------------------------------------------------ actions
# Each validates, records the user's input, submits the FIRST step, returns.


async def start_create(db: Session, client, brief: str, character_id: str | None, *,
                       owner_id: str) -> Post:
    post = Post(owner_id=owner_id,
                character_id=character_id or settings.default_character_id, brief=brief,
                status="clarifying", clarify_transcript=json.dumps([]))
    db.add(post)
    return await _begin(db, client, post, "category", {})


async def start_clarify_answer(db: Session, client, post_id: str, answer: str) -> Post:
    post = get_post(db, post_id)
    _require_idle(post)
    if post.status != "clarifying":
        raise StepError(f"post {post_id} is not awaiting clarification (status={post.status})")
    transcript = _load_transcript(post)
    if not transcript or transcript[-1].get("answer") is not None:
        raise StepError(f"post {post_id} has no pending clarify question")
    transcript[-1]["answer"] = answer
    _save_transcript(post, transcript)
    return await _begin(db, client, post, "clarify", {})


async def start_additional_info(db: Session, client, post_id: str, info: str) -> Post:
    """Human's answer to a needs_input escalation: a fresh automatic attempt
    (no cap on how often the human may do this)."""
    post = get_post(db, post_id)
    _require_idle(post)
    if post.status != "needs_input":
        raise StepError(f"post {post_id} is not awaiting additional input (status={post.status})")
    transcript = _transcript(post)
    transcript.append({"question": post.escalation_reason, "answer": info})
    _save_transcript(post, transcript)
    return await _begin(db, client, post, "draft", {"automatic": True, "attempt": 1})


def _require_drafting(post: Post) -> None:
    _require_idle(post)
    if post.status != "drafting":
        raise StepError(f"post {post.id} is not in drafting state (status={post.status})")


async def start_redraft(db: Session, client, post_id: str) -> Post:
    post = get_post(db, post_id)
    _require_drafting(post)
    return await _begin(db, client, post, "draft", {"automatic": False})


async def start_regenerate(db: Session, client, post_id: str, instruction: str) -> Post:
    post = get_post(db, post_id)
    _require_drafting(post)
    return await _begin(db, client, post, "rewrite",
                        {"automatic": False, "instruction": instruction})


async def start_lock(db: Session, client, post_id: str) -> Post:
    post = get_post(db, post_id)
    _require_drafting(post)
    return await _begin(db, client, post, "scene", {})


async def start_image(db: Session, client, post_id: str, profile: str = "full") -> Post:
    post = get_post(db, post_id)
    _require_idle(post)
    if post.status not in ("locked", "image_failed", "image_ready"):
        raise StepError(f"post {post_id} is not locked or retryable (status={post.status})")
    # A retry/re-roll needs a fresh seed: ComfyUI caches per-node outputs by
    # exact inputs, so the same seed would replay the previous (bad) result.
    if post.status in ("image_failed", "image_ready"):
        post.seed = random.randint(1, 999_999)
    post.status = "image_queued"
    post.image_started_at = datetime.utcnow()
    post.image_job_error = None
    post.image_profile = profile
    return await _begin(db, client, post, "image", {"profile": profile})


async def retry_step(db: Session, client, post_id: str) -> Post:
    """Resubmit the step that failed, from its stored context. User-initiated
    only -- nothing retries automatically."""
    post = get_post(db, post_id)
    _require_idle(post)
    ctx = _ctx(post)
    step = ctx.pop("_retry", None)
    if not step:
        raise StepError(f"post {post_id} has no failed step to retry")
    if step == "image":
        return await start_image(db, client, post_id, ctx.get("profile", "full"))
    return await _begin(db, client, post, step, ctx)
