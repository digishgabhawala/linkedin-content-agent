from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Post, PostDraft, SceneAsset
from ..services import feedback_service as fs
from ..services import image_service as isvc
from ..services import post_service as ps

router = APIRouter(prefix="/api")


async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client


# --------------------------------------------------------------------------
# request schemas
# --------------------------------------------------------------------------

class CreatePostRequest(BaseModel):
    brief: str
    character_id: str | None = None


class ClarifyRequest(BaseModel):
    answer: str


class RegenerateRequest(BaseModel):
    instruction: str


class AdditionalInfoRequest(BaseModel):
    info: str


class SceneUpdateRequest(BaseModel):
    scene_instruction: str


class SceneAssetUpdateRequest(BaseModel):
    detail_text: str


class FeedbackRequest(BaseModel):
    stage: str
    user_note: str
    post_text_snippet: str | None = None


# --------------------------------------------------------------------------
# serialization
# --------------------------------------------------------------------------

def _image_url(post: Post) -> str | None:
    if post.final_image_path:
        # A full external URL (Supabase Storage, via the task-queue's
        # artifact store) once image generation moved off direct
        # subprocess.Popen -- vs. the older convention of a local
        # filesystem path served under our own /generated mount. Both
        # still occur: existing rows from before this change hold a local
        # path, new ones hold a URL.
        if post.final_image_path.startswith(("http://", "https://")):
            return post.final_image_path
        return f"/generated/images/{Path(post.final_image_path).name}"
    placeholder = isvc.ensure_placeholder_image(post.character_id)
    return f"/generated/images/{placeholder.name}" if placeholder else None


def _serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "character_id": post.character_id,
        "brief": post.brief,
        "status": post.status,
        "pending_question": ps.pending_clarify_question(post),
        "clarify_transcript": json.loads(post.clarify_transcript) if post.clarify_transcript else [],
        "post_text": post.post_text,
        "draft_version": post.draft_version,
        "category": post.category,
        "gate_scores": json.loads(post.gate_scores) if post.gate_scores else {},
        "pillar_scores": json.loads(post.pillar_scores) if post.pillar_scores else {},
        "weighted_score": post.weighted_score,
        "recalibration_count": post.recalibration_count,
        "escalation_reason": post.escalation_reason,
        "scene_instruction": post.scene_instruction,
        "scene_asset_name": post.scene_asset_name,
        "seed": post.seed,
        "image_url": _image_url(post),
        "has_final_image": post.final_image_path is not None,
        "image_job_error": post.image_job_error,
        "is_stalled": isvc.is_stalled(post),
        "image_started_at": post.image_started_at.isoformat() if post.image_started_at else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


def _serialize_draft(draft: PostDraft) -> dict:
    return {
        "id": draft.id,
        "version": draft.version,
        "post_text": draft.post_text,
        "generated_by": draft.generated_by,
        "user_instruction": draft.user_instruction,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


def _serialize_feedback(fb) -> dict:
    return {
        "id": fb.id,
        "stage": fb.stage,
        "user_note": fb.user_note,
        "post_text_snippet": fb.post_text_snippet,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }


def _post_or_404(db: Session, post_id: str) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"post {post_id} not found")
    return post


def _serialize_scene_asset(asset: SceneAsset) -> dict:
    return {
        "name": asset.name,
        "detail_text": asset.detail_text,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/posts")
async def create_post(req: CreatePostRequest, db: Session = Depends(get_db),
                      client: httpx.AsyncClient = Depends(get_http_client)):
    post = await ps.create_post(db, client, req.brief, character_id=req.character_id)
    return _serialize_post(post)


@router.get("/posts")
def list_posts(db: Session = Depends(get_db)):
    return [_serialize_post(p) for p in ps.list_posts(db)]


@router.get("/posts/{post_id}")
async def get_post(post_id: str, db: Session = Depends(get_db),
                   client: httpx.AsyncClient = Depends(get_http_client)):
    post = _post_or_404(db, post_id)
    post = await isvc.sync_image_task(db, client, post)
    return _serialize_post(post)


@router.post("/posts/{post_id}/clarify")
async def clarify(post_id: str, req: ClarifyRequest, db: Session = Depends(get_db),
                  client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.submit_clarify_answer(db, client, post_id, req.answer)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/additional-info")
async def additional_info(post_id: str, req: AdditionalInfoRequest, db: Session = Depends(get_db),
                          client: httpx.AsyncClient = Depends(get_http_client)):
    """Human's response to a needs_input escalation (see post_service.py's
    _draft_and_score) -- unbounded, unlike the automatic recalibration loop."""
    _post_or_404(db, post_id)
    try:
        post = await ps.submit_additional_info(db, client, post_id, req.info)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/accept-draft")
def accept_draft(post_id: str, db: Session = Depends(get_db)):
    """Human's call to proceed with the current best draft despite an
    escalation notice -- the human is always the final gate."""
    _post_or_404(db, post_id)
    try:
        post = ps.accept_current_draft(db, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/draft")
async def redraft(post_id: str, db: Session = Depends(get_db),
                  client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.redraft_post(db, client, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/regenerate")
async def regenerate(post_id: str, req: RegenerateRequest, db: Session = Depends(get_db),
                     client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.regenerate_post_draft(db, client, post_id, req.instruction)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.get("/posts/{post_id}/drafts")
def get_drafts(post_id: str, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    return [_serialize_draft(d) for d in ps.list_drafts(db, post_id)]


@router.post("/posts/{post_id}/feedback")
def add_feedback(post_id: str, req: FeedbackRequest, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    fb = fs.create_feedback(db, post_id, req.stage, req.user_note, req.post_text_snippet)
    return _serialize_feedback(fb)


@router.get("/posts/{post_id}/feedback")
def get_feedback(post_id: str, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    return [_serialize_feedback(fb) for fb in fs.list_feedback(db, post_id)]


@router.post("/posts/{post_id}/lock")
async def lock(post_id: str, db: Session = Depends(get_db),
               client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.lock_post(db, client, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.patch("/posts/{post_id}/scene")
def update_scene(post_id: str, req: SceneUpdateRequest, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    try:
        post = ps.update_scene(db, post_id, req.scene_instruction)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/generate-image")
async def generate_image(post_id: str, db: Session = Depends(get_db),
                         client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await isvc.start_image_generation(db, client, post_id)
    except isvc.ImageServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/finalize")
def finalize(post_id: str, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    try:
        post = ps.finalize_post(db, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.get("/scene-assets")
def list_scene_assets(db: Session = Depends(get_db)):
    return [_serialize_scene_asset(a) for a in ps.list_scene_assets(db)]


@router.patch("/scene-assets/{name}")
def update_scene_asset(name: str, req: SceneAssetUpdateRequest, db: Session = Depends(get_db)):
    try:
        asset = ps.update_scene_asset(db, name, req.detail_text)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_scene_asset(asset)


@router.delete("/scene-assets/{name}")
def delete_scene_asset(name: str, db: Session = Depends(get_db)):
    """Deletes the stored asset so the next post whose scene proposes this
    same name seeds a fresh description -- the "I don't want the same
    coffee shop again" flow."""
    try:
        ps.delete_scene_asset(db, name)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}
