from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Post, PostDraft
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


class SceneUpdateRequest(BaseModel):
    scene_instruction: str


class FeedbackRequest(BaseModel):
    stage: str
    user_note: str
    post_text_snippet: str | None = None


class ImageCallbackRequest(BaseModel):
    job_id: str
    ok: bool
    image_path: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------
# serialization
# --------------------------------------------------------------------------

def _image_url(post: Post) -> str | None:
    if post.final_image_path:
        return f"/data/images/{Path(post.final_image_path).name}"
    placeholder = isvc.ensure_placeholder_image(post.character_id)
    return f"/data/images/{placeholder.name}" if placeholder else None


def _serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "character_id": post.character_id,
        "brief": post.brief,
        "status": post.status,
        "pending_question": ps.pending_clarify_question(post),
        "post_text": post.post_text,
        "draft_version": post.draft_version,
        "scene_instruction": post.scene_instruction,
        "seed": post.seed,
        "image_url": _image_url(post),
        "has_final_image": post.final_image_path is not None,
        "image_job_error": post.image_job_error,
        "is_stalled": isvc.is_stalled(post),
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
def get_post(post_id: str, db: Session = Depends(get_db)):
    return _serialize_post(_post_or_404(db, post_id))


@router.post("/posts/{post_id}/clarify")
async def clarify(post_id: str, req: ClarifyRequest, db: Session = Depends(get_db),
                  client: httpx.AsyncClient = Depends(get_http_client)):
    _post_or_404(db, post_id)
    try:
        post = await ps.submit_clarify_answer(db, client, post_id, req.answer)
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
def generate_image(post_id: str, db: Session = Depends(get_db)):
    _post_or_404(db, post_id)
    try:
        post = isvc.start_image_generation(db, post_id)
    except isvc.ImageBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
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


@router.post("/internal/image-callback")
def image_callback(req: ImageCallbackRequest, db: Session = Depends(get_db)):
    """Called only by the forge2 subprocess (see image_service.py), never
    by the frontend."""
    try:
        isvc.handle_image_callback(db, req.job_id, req.ok, req.image_path, req.error)
    except isvc.ImageServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}
