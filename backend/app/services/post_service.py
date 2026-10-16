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
import re
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Post, PostDraft, SceneAsset, SceneAssetVersion


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


def pending_clarify_question(post: Post) -> str | None:
    transcript = _load_transcript(post)
    if transcript and transcript[-1].get("answer") is None:
        return transcript[-1]["question"]
    return None


def accept_current_draft(db: Session, post_id: str) -> Post:
    """Human's call to proceed with the current best draft despite an
    escalation notice -- always available, per explicit design decision that
    the human is the final gate."""
    post = get_post(db, post_id)
    if post.status != "needs_input":
        raise PostServiceError(f"post {post_id} is not awaiting a decision "
                               f"(status={post.status})")
    post.status = "drafting"
    post.step_error = None  # a failed step's Retry no longer applies
    post.step_context = None
    db.commit()
    db.refresh(post)
    return post


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")


def _display_name(name: str) -> str:
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


_REF_PATTERN = re.compile(r"@([a-z0-9_]+)")


def _next_scene_asset_version(db: Session, name: str) -> int:
    latest = db.query(func.max(SceneAssetVersion.version)).filter(
        SceneAssetVersion.scene_asset_name == name).scalar()
    return (latest or 0) + 1


def _create_scene_asset_version(
    db: Session, name: str, version: int, detail_text: str,
) -> SceneAssetVersion:
    revision = SceneAssetVersion(
        scene_asset_name=name, version=version, detail_text=detail_text)
    db.add(revision)
    db.flush()
    return revision


def _current_scene_asset_version(db: Session, asset: SceneAsset) -> SceneAssetVersion:
    revision = db.query(SceneAssetVersion).filter(
        SceneAssetVersion.scene_asset_name == asset.name,
        SceneAssetVersion.version == asset.current_version,
    ).first()
    if revision is None:
        revision = _create_scene_asset_version(
            db, asset.name, asset.current_version, asset.detail_text)
    return revision


def _resolve_scene_asset(
    db: Session, scene: dict,
) -> tuple[str | None, str | None, str | None]:
    """scene_agent only ever PROPOSES a setting name + detail text -- this
    decides whether to reuse an existing SceneAsset (persisting a brand new
    one the first time a name appears, whatever was proposed this time
    becomes the seed every future post with that name will reuse) or just
    reference an already-known one. Returns (setting_placeholder, asset_name).

    This returns a short "@name" REFERENCE, not
    the full detail text -- the full text is only ever looked up at render
    time, by expand_scene_refs(), never baked into Post.scene_instruction.
    The post separately pins an immutable version id, so the stored scene
    stays readable ("adjusting a dial, @office, focused") without letting a
    later backdrop edit silently change an old post's render.

    asset_name is None whenever this scene has no named recurring setting,
    in which case the raw one-off setting_detail is returned as-is (nothing
    to reference by name -- see scene_agent's minimal-grounding docs for why
    this is never dropped even for unnamed metaphor scenes). The third return
    value pins the immutable backdrop revision used by this post."""
    name = scene.get("setting_name")
    if not name:
        return scene.get("setting_detail"), None, None
    slug = _slugify(str(name))
    if not slug:
        return scene.get("setting_detail"), None, None
    existing = db.query(SceneAsset).filter(SceneAsset.name == slug).first()
    if not existing:
        detail = scene.get("setting_detail")
        if not detail:
            return None, None, None
        version = _next_scene_asset_version(db, slug)
        existing = SceneAsset(
            name=slug,
            display_name=_display_name(slug),
            detail_text=detail,
            current_version=version,
        )
        db.add(existing)
        db.flush()
        revision = _create_scene_asset_version(db, slug, version, detail)
    elif existing.archived_at is not None:
        # Archived backdrops are retained for history but no longer reused by
        # the scene agent. Its proposed detail remains a one-off setting.
        return scene.get("setting_detail"), None, None
    else:
        revision = _current_scene_asset_version(db, existing)
    return f"@{slug}", slug, revision.id


def _assemble_scene_text(scene: dict, setting_detail: str | None) -> str:
    parts = [scene["action"]]
    if setting_detail:
        parts.append(setting_detail)
    parts.append(scene["angle"])
    parts.append(scene["mood"])
    return ", ".join(p for p in parts if p)


def expand_scene_refs(
    db: Session,
    scene_instruction: str,
    pinned_asset_name: str | None = None,
    pinned_version_id: str | None = None,
) -> str:
    """Expand every "@name" just before the image task is submitted.

    The post's primary backdrop uses its pinned immutable revision. Other
    unpinned references use the active version. A missing unpinned asset is
    dropped rather than leaving a stray "@" token for the image model, and
    resulting punctuation/whitespace is cleaned up.
    """
    pinned = db.get(SceneAssetVersion, pinned_version_id) if pinned_version_id else None
    if pinned_version_id and pinned is None:
        raise PostServiceError(f"backdrop version {pinned_version_id!r} not found")

    def _replace(m: re.Match) -> str:
        if pinned is not None and m.group(1) == pinned_asset_name:
            return pinned.detail_text
        asset = db.query(SceneAsset).filter(
            SceneAsset.name == m.group(1),
            SceneAsset.archived_at.is_(None),
        ).first()
        return asset.detail_text if asset else ""

    expanded = _REF_PATTERN.sub(_replace, scene_instruction)
    expanded = re.sub(r",\s*,", ",", expanded)
    expanded = re.sub(r"\s{2,}", " ", expanded)
    return expanded.strip(" ,")


def update_scene(db: Session, post_id: str, scene_instruction: str) -> Post:
    """Let the user edit the scene text -- either before the first render
    (status=="locked") or after seeing a finished/failed image and wanting a
    small targeted change (status in image_ready/image_failed) before
    clicking regenerate, e.g. "drop the cube, keep everything else." Not
    valid while image_queued -- a render is actively using the current text.
    If the edited text contains an @backdrop reference, pin its current
    immutable revision. Otherwise clear backdrop metadata."""
    post = get_post(db, post_id)
    if post.status not in ("locked", "image_ready", "image_failed"):
        raise PostServiceError(
            f"post {post_id} scene can't be edited mid-render (status={post.status})")
    post.scene_instruction = scene_instruction
    match = _REF_PATTERN.search(scene_instruction)
    asset = (db.query(SceneAsset).filter(
        SceneAsset.name == match.group(1),
        SceneAsset.archived_at.is_(None),
    ).first()
             if match else None)
    if asset is None:
        post.scene_asset_name = None
        post.scene_asset_version_id = None
    else:
        post.scene_asset_name = asset.name
        post.scene_asset_version_id = _current_scene_asset_version(db, asset).id
    if post.status in ("image_ready", "image_failed"):
        # The existing image depicts the old prompt; require a fresh render
        # before this post can be finalized again.
        post.status = "locked"
        post.image_job_error = None
    db.commit()
    db.refresh(post)
    return post


def list_scene_assets(db: Session, include_archived: bool = False) -> list[SceneAsset]:
    query = db.query(SceneAsset)
    if not include_archived:
        query = query.filter(SceneAsset.archived_at.is_(None))
    return query.order_by(SceneAsset.display_name.asc(), SceneAsset.name.asc()).all()


def create_scene_asset(db: Session, display_name: str, detail_text: str) -> SceneAsset:
    label = display_name.strip()
    detail = detail_text.strip()
    name = _slugify(label)
    if not label or not name:
        raise PostServiceError("backdrop display name must contain letters or numbers")
    if len(name) > 64:
        raise PostServiceError("backdrop identifier must be 64 characters or fewer")
    if not detail:
        raise PostServiceError("backdrop description is required")
    existing = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if existing is not None:
        state = "archived" if existing.archived_at is not None else "active"
        raise PostServiceError(
            f"backdrop @{name} already exists and is {state}; choose a different name")
    version = _next_scene_asset_version(db, name)
    asset = SceneAsset(
        name=name,
        display_name=label,
        detail_text=detail,
        current_version=version,
    )
    db.add(asset)
    db.flush()
    _create_scene_asset_version(db, name, version, detail)
    db.commit()
    db.refresh(asset)
    return asset


def update_scene_asset(
    db: Session,
    name: str,
    detail_text: str,
    display_name: str | None = None,
) -> SceneAsset:
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    detail = detail_text.strip()
    if not detail:
        raise PostServiceError("backdrop description is required")
    label = display_name.strip() if display_name is not None else None
    if display_name is not None and not label:
        raise PostServiceError("backdrop display name is required")
    label_changed = label is not None and label != asset.display_name
    if label_changed:
        asset.display_name = label
    if detail == asset.detail_text:
        if label_changed:
            db.commit()
            db.refresh(asset)
        return asset
    version = _next_scene_asset_version(db, name)
    _create_scene_asset_version(db, name, version, detail)
    asset.detail_text = detail
    asset.current_version = version
    db.commit()
    db.refresh(asset)
    return asset


def list_scene_asset_versions(db: Session, name: str) -> list[SceneAssetVersion]:
    return db.query(SceneAssetVersion).filter(
        SceneAssetVersion.scene_asset_name == name,
    ).order_by(SceneAssetVersion.version.desc()).all()


def scene_asset_usage_posts(
    db: Session, name: str, version_id: str | None = None,
) -> list[Post]:
    query = db.query(Post).filter(Post.scene_asset_name == name)
    if version_id is not None:
        query = query.filter(Post.scene_asset_version_id == version_id)
    return query.order_by(Post.updated_at.desc(), Post.created_at.desc()).all()


def archive_scene_asset(db: Session, name: str) -> SceneAsset:
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    if asset.archived_at is None:
        asset.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(asset)
    return asset


def unarchive_scene_asset(db: Session, name: str) -> SceneAsset:
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    if asset.archived_at is not None:
        asset.archived_at = None
        db.commit()
        db.refresh(asset)
    return asset


def restore_scene_asset_version(db: Session, name: str, version: int) -> SceneAsset:
    asset = db.query(SceneAsset).filter(SceneAsset.name == name).first()
    if asset is None:
        raise PostServiceError(f"scene asset {name!r} not found")
    historical = db.query(SceneAssetVersion).filter(
        SceneAssetVersion.scene_asset_name == name,
        SceneAssetVersion.version == version,
    ).first()
    if historical is None:
        raise PostServiceError(f"scene asset {name!r} version {version} not found")
    next_version = _next_scene_asset_version(db, name)
    _create_scene_asset_version(db, name, next_version, historical.detail_text)
    asset.detail_text = historical.detail_text
    asset.current_version = next_version
    asset.archived_at = None
    db.commit()
    db.refresh(asset)
    return asset


def _clean_scene_refs(scene_instruction: str, name: str | None = None) -> str:
    if name:
        cleaned = re.sub(rf"@{re.escape(name)}\b", "", scene_instruction)
    else:
        cleaned = _REF_PATTERN.sub("", scene_instruction, count=1)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,")


def set_post_scene_asset(db: Session, post_id: str, name: str | None) -> Post:
    """Select or clear the post's primary recurring backdrop."""
    post = get_post(db, post_id)
    if post.status not in ("locked", "image_ready", "image_failed"):
        raise PostServiceError(
            f"post {post_id} backdrop can't be changed mid-render (status={post.status})")
    scene = post.scene_instruction or ""
    old_name = post.scene_asset_name
    if name is None:
        post.scene_instruction = _clean_scene_refs(scene, old_name)
        post.scene_asset_name = None
        post.scene_asset_version_id = None
    else:
        asset = db.query(SceneAsset).filter(
            SceneAsset.name == name,
            SceneAsset.archived_at.is_(None),
        ).first()
        if asset is None:
            raise PostServiceError(f"active scene asset {name!r} not found")
        scene = _clean_scene_refs(scene, old_name)
        post.scene_instruction = f"{scene}, @{name}" if scene else f"@{name}"
        post.scene_asset_name = name
        post.scene_asset_version_id = _current_scene_asset_version(db, asset).id
    if post.status in ("image_ready", "image_failed"):
        post.status = "locked"
        post.image_job_error = None
    db.commit()
    db.refresh(post)
    return post


def use_latest_scene_asset(db: Session, post_id: str) -> Post:
    """Pin the active backdrop revision and require a fresh image render.

    An already-rendered image still depicts the older revision, so moving an
    image_ready/image_failed post back to locked prevents it from being
    finalized under mismatched backdrop metadata.
    """
    post = get_post(db, post_id)
    if post.status not in ("locked", "image_ready", "image_failed"):
        raise PostServiceError(
            f"post {post_id} backdrop can't be changed mid-render (status={post.status})")
    if not post.scene_asset_name:
        raise PostServiceError(f"post {post_id} does not reference a recurring backdrop")
    asset = db.query(SceneAsset).filter(
        SceneAsset.name == post.scene_asset_name,
        SceneAsset.archived_at.is_(None),
    ).first()
    if asset is None:
        raise PostServiceError(f"scene asset {post.scene_asset_name!r} is no longer active")
    post.scene_asset_version_id = _current_scene_asset_version(db, asset).id
    post.status = "locked"
    post.image_job_error = None
    db.commit()
    db.refresh(post)
    return post


def delete_scene_asset(db: Session, name: str) -> None:
    """Backward-compatible alias: old clients now archive instead of deleting."""
    archive_scene_asset(db, name)


def finalize_post(db: Session, post_id: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "image_ready":
        raise PostServiceError(f"post {post_id} has no ready image "
                               f"(status={post.status})")
    post.status = "ready"
    db.commit()
    db.refresh(post)
    return post
