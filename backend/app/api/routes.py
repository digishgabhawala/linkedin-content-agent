from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Post, PostDraft, SceneAsset
from ..services import feedback_service as fs
from ..services import image_service as isvc
from ..services import post_service as ps
from ..services.ollama_lifecycle import owned_ollama_session
from ..services.renderer_status_service import (
    hosted_image_readiness,
    hosted_renderer_status,
)

router = APIRouter(prefix="/api")


async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client


async def get_ollama_client():
    async with httpx.AsyncClient() as client, owned_ollama_session(client):
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


class GenerateImageRequest(BaseModel):
    profile: Literal["full", "lightning"] = "full"


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


def _utc_iso(value: datetime | None) -> str | None:
    """Serialize the database's naive datetimes as the UTC they represent.

    Without an offset, browsers interpret ISO timestamps as local time. On an
    IST machine that made a just-started render appear 330 minutes old.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
        "image_queue_status": getattr(post, "image_queue_status", None),
        "image_claimed_at": getattr(post, "image_claimed_at", None),
        "image_worker_id": getattr(post, "image_worker_id", None),
        "image_progress_stage": getattr(post, "image_progress_stage", None),
        "image_progress_message": getattr(post, "image_progress_message", None),
        "image_progress_updated_at": getattr(post, "image_progress_updated_at", None),
        "is_worker_lost": isvc.is_worker_lost(post),
        "image_failure_kind": isvc.image_failure_kind(post),
        "is_queue_delayed": isvc.is_queue_delayed(post),
        "is_stalled": isvc.is_stalled(post),
        "image_started_at": _utc_iso(post.image_started_at),
        "created_at": _utc_iso(post.created_at),
        "updated_at": _utc_iso(post.updated_at),
    }


def _serialize_draft(draft: PostDraft) -> dict:
    return {
        "id": draft.id,
        "version": draft.version,
        "post_text": draft.post_text,
        "generated_by": draft.generated_by,
        "user_instruction": draft.user_instruction,
        "created_at": _utc_iso(draft.created_at),
    }


def _serialize_feedback(fb) -> dict:
    return {
        "id": fb.id,
        "stage": fb.stage,
        "user_note": fb.user_note,
        "post_text_snippet": fb.post_text_snippet,
        "created_at": _utc_iso(fb.created_at),
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
        "created_at": _utc_iso(asset.created_at),
        "updated_at": _utc_iso(asset.updated_at),
    }


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/resources/image-readiness")
async def get_image_readiness(client: httpx.AsyncClient = Depends(get_http_client)):
    return await hosted_image_readiness(client)


@router.get("/resources/renderer-status")
async def get_renderer_status(client: httpx.AsyncClient = Depends(get_http_client)):
    return await hosted_renderer_status(client)


@router.post("/posts")
async def create_post(req: CreatePostRequest, db: Session = Depends(get_db),
                      client: httpx.AsyncClient = Depends(get_ollama_client)):
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
                  client: httpx.AsyncClient = Depends(get_ollama_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.submit_clarify_answer(db, client, post_id, req.answer)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/additional-info")
async def additional_info(post_id: str, req: AdditionalInfoRequest, db: Session = Depends(get_db),
                          client: httpx.AsyncClient = Depends(get_ollama_client)):
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
                  client: httpx.AsyncClient = Depends(get_ollama_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.redraft_post(db, client, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/regenerate")
async def regenerate(post_id: str, req: RegenerateRequest, db: Session = Depends(get_db),
                     client: httpx.AsyncClient = Depends(get_ollama_client)):
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
               client: httpx.AsyncClient = Depends(get_ollama_client)):
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
async def generate_image(post_id: str, req: GenerateImageRequest | None = None,
                         db: Session = Depends(get_db),
                         client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await isvc.start_image_generation(
            db, client, post_id, profile=req.profile if req else "full")
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
