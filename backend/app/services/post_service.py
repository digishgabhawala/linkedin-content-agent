"""post_service.py -- orchestrates the Post state machine.

clarifying -> [needs_input <-> drafting] -> locked -> image_queued ->
image_ready|image_failed -> ready

Clarify transcript is stored as a JSON list of {"question", "answer"} on
Post.clarify_transcript. A pending (unanswered) question is represented as
the last entry with answer=None; only fully-answered turns are ever passed
to draft_agent (see _answered_turns).

As of the content-quality redesign (CONTENT_QUALITY_DESIGN.md), reaching
"drafting" is no longer a single generate_draft() call -- it's category
inference (once, during clarify) followed by a draft+score+recalibrate loop
(_draft_and_score) capped at settings.max_recalibration_passes automatic
passes. A pillar failure that rewriting can't fix (needs new material or a
different angle -- see taxonomy.FIX_TYPE) escalates to "needs_input" instead
of burning automatic passes on something a rewrite can't solve. The human is
always the final call: accept the current best draft as-is (needs_input ->
drafting) or provide more input and let it try again (unbounded, no cap --
the 3-pass cap is for the automatic loop only, per explicit design decision).

image_queued/image_ready/image_failed/ready transitions live in
image_service.py, not here -- this module only goes as far as "locked".
"""
from __future__ import annotations

import json
import random
import re

import httpx
from sqlalchemy.orm import Session

from ..agents.category_agent import infer_category
from ..agents.content_sources import load_character_personality, load_user_profile
from ..agents.draft_agent import (
    build_escalation_message,
    clarify_turn,
    generate_draft,
    regenerate_draft,
)
from ..agents.judge_agent import score_post
from ..agents.scene_agent import derive_scene
from ..agents.taxonomy import (
    FIX_TYPE,
    GATE_PILLARS,
    GATE_THRESHOLD,
    OPTIMIZATION_PILLARS,
    RECALIBRATION_THRESHOLD,
    weighted_score,
)
from ..config import settings
from ..db.models import Post, PostDraft, SceneAsset


class PostServiceError(Exception):
    """Raised for invalid state transitions (wrong status for the requested action)."""


def _load_transcript(post: Post) -> list[dict]:
    if not post.clarify_transcript:
        return []
    return json.loads(post.clarify_transcript)


def _save_transcript(post: Post, transcript: list[dict]) -> None:
    post.clarify_transcript = json.dumps(transcript)


def _answered_turns(transcript: list[dict]) -> list[dict]:
    return [t for t in transcript if t.get("answer") is not None]


def get_post(db: Session, post_id: str) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise PostServiceError(f"post {post_id} not found")
    return post


def list_posts(db: Session) -> list[Post]:
    return db.query(Post).order_by(Post.created_at.desc()).all()


def list_drafts(db: Session, post_id: str) -> list[PostDraft]:
    return (db.query(PostDraft)
            .filter(PostDraft.post_id == post_id)
            .order_by(PostDraft.version.asc())
            .all())


def _all_scores(gate_scores: dict, pillar_scores: dict) -> dict:
    merged = dict(gate_scores)
    merged.update(pillar_scores)
    return merged


_LENGTH_RICHNESS_THRESHOLD = 300  # chars of real material (brief + answered transcript)
_MIN_MATERIAL_CHARS = 300         # below this, no rewrite can help -- ask the human instead


def _material_chars(brief: str, transcript: list[dict]) -> int:
    return len(brief) + sum(len(t.get("answer") or "") for t in transcript)


def _length_fit_score(n: int) -> float:
    """Deterministic length_fit bands around skill.md's 1500-2200 target
    (upper bands reflect LinkedIn's ~3000-char truncation). 900-1200 lands
    exactly AT the 6.5 recalibration threshold on purpose: an honest amber
    signal to the human without burning automatic passes on the model's
    known ~1100-char plateau."""
    if n < 600:
        return 3.0
    if n < 900:
        return 5.0
    if n < 1200:
        return 6.5
    if n < 1500:
        return 8.0
    if n <= 2200:
        return 10.0
    if n <= 2600:
        return 8.0
    if n <= 3000:
        return 6.0
    return 4.0


def _apply_length_fit(scores: dict, draft_text: str, brief: str, transcript: list[dict]) -> None:
    """Overwrites the judge's length_fit with a deterministic score. The judge
    scored clearly-short drafts 8-10/10 on this pillar in every live test,
    even with the target numbers spelled out in its rubric -- and unlike the
    other pillars, length needs no LLM judgment at all: it's measurable. The
    judge still returns a length_fit entry (keeping its JSON schema stable);
    it is discarded here. A high or low score is now always an honest
    reflection of actual character count, so the human can take their own
    call on an under-length post instead of being shown a 10/10."""
    n = len(draft_text)
    material = _material_chars(brief, transcript)
    score = _length_fit_score(n)
    if 1500 <= n <= 2200:
        reason = f"{n} chars -- inside the 1500-2200 target range."
    elif n < 1500 and material < _LENGTH_RICHNESS_THRESHOLD:
        reason = (f"{n} chars, under the 1500-2200 target -- but the brief/clarification "
                  f"only holds ~{material} chars of real material, so a longer post would "
                  "need invented facts. Add real material to support a longer post.")
    elif n < 1500:
        reason = (f"{n} chars, under the 1500-2200 target, with ~{material} chars of real "
                  "material available. Scored deterministically from actual length -- decide "
                  "whether this length is acceptable or push for a fuller post.")
    else:
        reason = (f"{n} chars, over the 2200 upper bound -- LinkedIn truncates around "
                  "3000 and long posts lose readers; consider tightening.")
    scores["length_fit"] = {"score": score, "reason": reason}


async def _rescore(client: httpx.AsyncClient, post: Post) -> None:
    """Recomputes gate/pillar scores against post.post_text as it currently
    stands and updates the post in place. Manual redraft/regenerate used to
    leave the previous scores untouched, which silently desynced the
    displayed scores/reasons from the actual text on screen -- found live
    when a redrafted post still showed a score's reasoning quoting the OLD
    text. Every text-changing action must call this, not just the automatic
    recalibration loop."""
    character_personality = load_character_personality(post.character_id)
    user_profile = load_user_profile()
    transcript = _answered_turns(_load_transcript(post))
    scores = await score_post(client, post.post_text, post.brief, transcript,
                              post.category, character_personality, user_profile)
    _apply_length_fit(scores, post.post_text, post.brief, transcript)
    post.gate_scores = json.dumps({p: scores[p] for p in GATE_PILLARS})
    post.pillar_scores = json.dumps({p: scores[p] for p in OPTIMIZATION_PILLARS})
    post.weighted_score = weighted_score(
        post.category, {p: scores[p]["score"] for p in OPTIMIZATION_PILLARS})


async def _draft_and_score(db: Session, client: httpx.AsyncClient, post: Post,
                           transcript: list[dict]) -> None:
    """Runs draft -> score -> (recalibrate up to max_recalibration_passes |
    escalate) and leaves post.status as either "drafting" (a usable draft is
    ready, whether perfect or the best automatic recalibration could do) or
    "needs_input" (a pillar failure needs new material/a different angle from
    the human before continuing). Mutates `post` in place; caller commits."""
    character_personality = load_character_personality(post.character_id)
    user_profile = load_user_profile()
    material = _material_chars(post.brief, transcript)

    draft_text = await generate_draft(client, post.brief, transcript, post.character_id, post.category)
    version = post.draft_version + 1
    db.add(PostDraft(post_id=post.id, version=version, post_text=draft_text,
                     generated_by="draft", user_instruction=None))
    attempt = 1

    while True:
        scores = await score_post(client, draft_text, post.brief, transcript,
                                  post.category, character_personality, user_profile)
        _apply_length_fit(scores, draft_text, post.brief, transcript)
        gate_scores = {p: scores[p] for p in GATE_PILLARS}
        pillar_scores = {p: scores[p] for p in OPTIMIZATION_PILLARS}

        failing = []
        for pillar in GATE_PILLARS:
            if scores[pillar]["score"] < GATE_THRESHOLD:
                failing.append({"pillar": pillar, "reason": scores[pillar]["reason"],
                               "fix_type": FIX_TYPE[pillar]})
        for pillar in OPTIMIZATION_PILLARS:
            if scores[pillar]["score"] < RECALIBRATION_THRESHOLD:
                failing.append({"pillar": pillar, "reason": scores[pillar]["reason"],
                               "fix_type": FIX_TYPE[pillar]})

        needs_escalation = [f for f in failing if f["fix_type"] != "rewrite"]

        post.post_text = draft_text
        post.draft_version = version
        post.gate_scores = json.dumps(gate_scores)
        post.pillar_scores = json.dumps(pillar_scores)
        post.weighted_score = weighted_score(post.category, {p: s["score"] for p, s in pillar_scores.items()})
        post.recalibration_count = attempt

        # Thin-material gate (deterministic, checked before anything else): if
        # the brief + clarification just don't contain enough real substance,
        # no amount of rewriting fixes it -- and the writer isn't allowed to
        # invent. Garbage in, garbage out: stop after one honest best-effort
        # draft and ask the human for material, instead of burning
        # recalibration passes or presenting a thin post as a success.
        if material < _MIN_MATERIAL_CHARS:
            post.escalation_reason = await build_escalation_message(
                client, post.brief, post.category,
                [{"pillar": "material_sufficiency", "fix_type": "needs_material",
                  "reason": (f"the brief plus clarification total only ~{material} "
                             "characters of real material -- not enough to build a "
                             "strong post without inventing facts. A short honest "
                             "draft exists as a starting point, but it needs real "
                             "additional detail (mechanism, numbers, what was tried, "
                             "why it mattered) to become a good post.")}])
            post.status = "needs_input"
            return

        if needs_escalation:
            post.escalation_reason = await build_escalation_message(
                client, post.brief, post.category, needs_escalation)
            post.status = "needs_input"
            return

        if not failing:
            post.escalation_reason = None
            post.status = "drafting"
            return

        if attempt >= settings.max_recalibration_passes:
            # Exhausted automatic passes but rewrite-fixable pillars are still
            # short -- surface as best-effort rather than loop forever; human
            # decides whether to accept it or keep pushing manually (redraft/
            # regenerate stay available once status is "drafting").
            reasons = "; ".join(f"{f['pillar']} ({scores[f['pillar']]['score']}/10): {f['reason']}"
                                for f in failing)
            post.escalation_reason = (
                f"Automatic recalibration ({attempt} passes) couldn't fully clear every "
                f"pillar. Still short on: {reasons}. You can accept this draft as-is or "
                "keep refining it manually.")
            post.status = "drafting"  # not needs_input -- these are rewrite-fixable in
            # principle, just didn't converge in time; human can keep going via redraft/
            # regenerate rather than being blocked on providing new material.
            return

        critique = "Improve the following, based on specific critique:\n" + "\n".join(
            f"- {f['pillar']} ({scores[f['pillar']]['score']}/10): {f['reason']}"
            for f in failing)
        draft_text = await regenerate_draft(client, draft_text, critique, post.character_id, post.category)
        version += 1
        db.add(PostDraft(post_id=post.id, version=version, post_text=draft_text,
                         generated_by="recalibration", user_instruction=critique))
        attempt += 1


async def _advance_clarify(db: Session, client: httpx.AsyncClient, post: Post,
                           answered: list[dict]) -> Post:
    result = await clarify_turn(client, post.brief, answered, post.category)

    # Cap: force done once we've already asked clarify_max_turns questions,
    # regardless of what the model wants -- a thin brief stays thin rather
    # than looping forever asking for detail that isn't coming.
    if not result["done"] and len(answered) >= settings.clarify_max_turns:
        result = {"done": True, "question": None}

    if result["done"]:
        _save_transcript(post, answered)
        await _draft_and_score(db, client, post, answered)
    else:
        transcript = answered + [{"question": result["question"], "answer": None}]
        _save_transcript(post, transcript)
        # status stays "clarifying"

    db.commit()
    db.refresh(post)
    return post


async def create_post(db: Session, client: httpx.AsyncClient, brief: str,
                      character_id: str | None = None) -> Post:
    category = await infer_category(client, brief)
    post = Post(character_id=character_id or settings.default_character_id,
               brief=brief, status="clarifying", clarify_transcript=json.dumps([]),
               category=category)
    db.add(post)
    db.commit()
    db.refresh(post)
    return await _advance_clarify(db, client, post, [])


async def submit_clarify_answer(db: Session, client: httpx.AsyncClient, post_id: str,
                                answer: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "clarifying":
        raise PostServiceError(f"post {post_id} is not awaiting clarification "
                               f"(status={post.status})")
    transcript = _load_transcript(post)
    if not transcript or transcript[-1].get("answer") is not None:
        raise PostServiceError(f"post {post_id} has no pending clarify question")
    transcript[-1]["answer"] = answer
    return await _advance_clarify(db, client, post, _answered_turns(transcript))


def pending_clarify_question(post: Post) -> str | None:
    transcript = _load_transcript(post)
    if transcript and transcript[-1].get("answer") is None:
        return transcript[-1]["question"]
    return None


async def submit_additional_info(db: Session, client: httpx.AsyncClient, post_id: str,
                                 info: str) -> Post:
    """Human's response to a needs_input escalation -- appended to the
    clarify transcript (as a synthetic Q/A turn using the escalation message
    as the "question") and fed back through draft_and_score for a fresh
    attempt. Unlike the automatic recalibration loop, this has no cap -- the
    human can do this as many times as they want (explicit design decision:
    the 3-pass cap is for the automatic loop only)."""
    post = get_post(db, post_id)
    if post.status != "needs_input":
        raise PostServiceError(f"post {post_id} is not awaiting additional input "
                               f"(status={post.status})")
    transcript = _answered_turns(_load_transcript(post))
    transcript.append({"question": post.escalation_reason, "answer": info})
    _save_transcript(post, transcript)
    await _draft_and_score(db, client, post, transcript)
    db.commit()
    db.refresh(post)
    return post


def accept_current_draft(db: Session, post_id: str) -> Post:
    """Human's call to proceed with the current best draft despite an
    escalation notice -- always available, per explicit design decision that
    the human is the final gate."""
    post = get_post(db, post_id)
    if post.status != "needs_input":
        raise PostServiceError(f"post {post_id} is not awaiting a decision "
                               f"(status={post.status})")
    post.status = "drafting"
    db.commit()
    db.refresh(post)
    return post


async def redraft_post(db: Session, client: httpx.AsyncClient, post_id: str) -> Post:
    """Fresh draft from the original brief + clarification, discarding the
    current text -- a "start over" action distinct from regenerate's
    instruction-based revision of the existing draft. Manual, not part of the
    automatic recalibration loop -- but still re-scores, so the displayed
    pillar scores always match the text actually on screen."""
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    transcript = _answered_turns(_load_transcript(post))
    new_text = await generate_draft(client, post.brief, transcript, post.character_id, post.category)
    version = post.draft_version + 1
    db.add(PostDraft(post_id=post.id, version=version, post_text=new_text,
                     generated_by="draft", user_instruction=None))
    post.post_text = new_text
    post.draft_version = version
    await _rescore(client, post)
    db.commit()
    db.refresh(post)
    return post


async def regenerate_post_draft(db: Session, client: httpx.AsyncClient, post_id: str,
                                instruction: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    new_text = await regenerate_draft(client, post.post_text, instruction, post.character_id, post.category)
    version = post.draft_version + 1
    db.add(PostDraft(post_id=post.id, version=version, post_text=new_text,
                     generated_by="regenerate", user_instruction=instruction))
    post.post_text = new_text
    post.draft_version = version
    await _rescore(client, post)
    db.commit()
    db.refresh(post)
    return post


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")


_REF_PATTERN = re.compile(r"@([a-z0-9_]+)")


def _resolve_scene_asset(db: Session, scene: dict) -> tuple[str | None, str | None]:
    """scene_agent only ever PROPOSES a setting name + detail text -- this
    decides whether to reuse an existing SceneAsset (persisting a brand new
    one the first time a name appears, whatever was proposed this time
    becomes the seed every future post with that name will reuse) or just
    reference an already-known one. Returns (setting_placeholder, asset_name).

    IMPORTANT: as of 2026-08-02, this returns a short "@name" REFERENCE, not
    the full detail text -- the full text is only ever looked up at render
    time, by expand_scene_refs(), never baked into Post.scene_instruction.
    This was a direct user ask: the fully-expanded text made the saved scene
    long and hard to read/edit by hand, and baking it in also meant editing
    an asset's detail_text later never affected posts that had already
    locked with the old copy. A short reference fixes both -- the stored
    scene reads like "adjusting a dial, @office, focused" and always reflects
    whatever "office" currently means, even if edited after this post locked.

    asset_name is None whenever this scene has no named recurring setting,
    in which case the raw one-off setting_detail is returned as-is (nothing
    to reference by name -- see scene_agent's minimal-grounding docs for why
    this is never dropped even for unnamed metaphor scenes)."""
    name = scene.get("setting_name")
    if not name:
        return scene.get("setting_detail"), None
    slug = _slugify(str(name))
    if not slug:
        return scene.get("setting_detail"), None
    existing = db.query(SceneAsset).filter(SceneAsset.name == slug).first()
    if not existing:
        detail = scene.get("setting_detail")
        if not detail:
            return None, None
        db.add(SceneAsset(name=slug, detail_text=detail))
    return f"@{slug}", slug


def _assemble_scene_text(scene: dict, setting_detail: str | None) -> str:
    parts = [scene["action"]]
    if setting_detail:
        parts.append(setting_detail)
    parts.append(scene["angle"])
    parts.append(scene["mood"])
    return ", ".join(p for p in parts if p)


def expand_scene_refs(db: Session, scene_instruction: str) -> str:
    """Expands every "@name" reference in a scene_instruction into that
    SceneAsset's CURRENT detail_text. Called only right before the prompt is
    actually sent to forge2 (image_service.py) -- the expanded text is never
    persisted, so an asset edited or forgotten after a post locked is always
    reflected at render time. A reference to a since-forgotten asset expands
    to nothing (dropped, not left as a bare unresolved "@name" -- a stray "@"
    token would just confuse the image model) and any resulting double comma
    or extra whitespace from a dropped reference is cleaned up."""
    def _replace(m: re.Match) -> str:
        asset = db.query(SceneAsset).filter(SceneAsset.name == m.group(1)).first()
        return asset.detail_text if asset else ""

    expanded = _REF_PATTERN.sub(_replace, scene_instruction)
    expanded = re.sub(r",\s*,", ",", expanded)
    expanded = re.sub(r"\s{2,}", " ", expanded)
    return expanded.strip(" ,")


async def lock_post(db: Session, client: httpx.AsyncClient, post_id: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    scene = await derive_scene(client, post.post_text)
    setting_detail, asset_name = _resolve_scene_asset(db, scene)
    post.scene_instruction = _assemble_scene_text(scene, setting_detail)
    post.scene_asset_name = asset_name
    post.seed = random.randint(1, 999_999)
    post.status = "locked"
    db.commit()
    db.refresh(post)
    return post


def update_scene(db: Session, post_id: str, scene_instruction: str) -> Post:
    """Let the user edit the scene text -- either before the first render
    (status=="locked") or after seeing a finished/failed image and wanting a
    small targeted change (status in image_ready/image_failed) before
    clicking regenerate, e.g. "drop the cube, keep everything else." Not
    valid while image_queued -- a render is actively using the current text.
    Clears scene_asset_name: once hand-edited, the text is no longer
    guaranteed to reflect the stored asset it started from."""
    post = get_post(db, post_id)
    if post.status not in ("locked", "image_ready", "image_failed"):
        raise PostServiceError(
            f"post {post_id} scene can't be edited mid-render (status={post.status})")
    post.scene_instruction = scene_instruction
    post.scene_asset_name = None
    db.commit()
    db.refresh(post)
    return post


def list_scene_assets(db: Session) -> list[SceneAsset]:
    return db.query(SceneAsset).order_by(SceneAsset.name.asc()).all()


def update_scene_asset(db: Session, name: str, detail_text: str) -> SceneAsset:
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    asset.detail_text = detail_text
    db.commit()
    db.refresh(asset)
    return asset


def delete_scene_asset(db: Session, name: str) -> None:
    """The user's stated "I don't want the same coffee shop again" flow --
    delete the asset and the next post whose scene proposes that same name
    seeds a fresh detail description from scratch. No variant-numbering
    system (e.g. "coffee_shop_2") built for this yet -- simplest thing that
    satisfies the stated need; revisit only if losing the old description
    entirely turns out to matter in practice."""
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    db.delete(asset)
    db.commit()


def finalize_post(db: Session, post_id: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "image_ready":
        raise PostServiceError(f"post {post_id} has no ready image "
                               f"(status={post.status})")
    post.status = "ready"
    db.commit()
    db.refresh(post)
    return post
