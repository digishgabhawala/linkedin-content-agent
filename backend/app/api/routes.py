from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import AuthUser, current_user, public_auth_config
from ..config import settings
from ..db.database import get_db
from ..db.models import (
    Character,
    HeroCandidate,
    HeroGenerationRun,
    Post,
    PostDraft,
    SceneAsset,
    SceneAssetVersion,
)
from ..errors import ReasonedHTTPException
from ..services import feedback_service as fs
from ..services import hero_generation as hgs
from ..services import image_service as isvc
from ..services import post_service as ps
from ..services import profile_service, steps
from ..services.character_choice import (
    CharacterNotOwned,
    MascotRequired,
    choose_character,
)
from ..services.renderer_status_service import (
    hosted_image_readiness,
    hosted_renderer_status,
)

# Every route needs a signed-in, allowed user (app/auth.py) -- set once here
# so a new route can't be left open by mistake. Only public_router is open.
# Paths match the shared domain (aibharatiya.com/api/linkedin/...), so the
# parent site forwards them unchanged.
API_PREFIX = "/api/linkedin"
public_router = APIRouter(prefix=API_PREFIX)
router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(current_user)])


def _task_queue_headers() -> dict:
    # This app's own machine key for the task-queue (never a human session);
    # needed for admin-only reads such as GET /api/workers.
    key = settings.task_queue_api_key
    return {"X-API-Key": key} if key else {}


async def get_http_client():
    async with httpx.AsyncClient(headers=_task_queue_headers()) as client:
        yield client


async def get_llm_client():
    # LLM calls are task-queue tasks (see llm_client.py); the local worker
    # owns Ollama and its memory.
    async with httpx.AsyncClient(headers=_task_queue_headers()) as client:
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


class PostBackdropRequest(BaseModel):
    scene_asset_name: str | None = None


class PostCharacterRequest(BaseModel):
    character_id: str


class WriterProfileRequest(BaseModel):
    profile_md: str

    @model_validator(mode="after")
    def _within_limits(self) -> WriterProfileRequest:
        self.profile_md = self.profile_md.strip()
        if not self.profile_md:
            raise ValueError("the writer profile can't be empty")
        if len(self.profile_md) > profile_service.MAX_PROFILE_CHARS:
            raise ValueError(f"the writer profile is limited to "
                             f"{profile_service.MAX_PROFILE_CHARS} characters")
        return self


class SceneAssetCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    detail_text: str = Field(min_length=1, max_length=1500)


class SceneAssetUpdateRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=80)
    detail_text: str = Field(min_length=1, max_length=1500)


class FeedbackRequest(BaseModel):
    stage: str
    user_note: str
    post_text_snippet: str | None = None


class GenerateImageRequest(BaseModel):
    profile: Literal["full", "lightning"] = "full"


class SignatureAttributeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    prompt_phrase: str = Field(min_length=1, max_length=300)
    color_hex: str | None = Field(
        None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CharacterCardRequest(BaseModel):
    character_id: str = Field(
        pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    trigger_token: str | None = Field(None, max_length=100)
    display_name: str = Field("", max_length=100)
    style_tag: str = Field("flat vector cartoon mascot", min_length=1, max_length=300)
    species_or_type: str = Field("human", min_length=1, max_length=100)
    base_description: str = Field(min_length=1, max_length=1000)
    signature_attributes: list[SignatureAttributeRequest] = Field(
        default_factory=list, max_length=3)
    personality: str = Field("", max_length=1000)
    negative_traits: str = Field("", max_length=1000)
    notes: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def default_trigger_token(self):
        if not self.trigger_token:
            self.trigger_token = self.character_id
        return self


class HeroGenerationRequest(BaseModel):
    candidate_count: int = Field(4, ge=1, le=hgs.MAX_CANDIDATES_PER_RUN)
    base_seed: int | None = Field(None, ge=0)
    profile: Literal["full", "lightning"] = "full"


# --------------------------------------------------------------------------
# serialization
# --------------------------------------------------------------------------

def _image_url(post: Post) -> str | None:
    # The post's own render (a Supabase Storage URL), else the mascot's hero
    # image as a placeholder. Old local file paths are no longer servable.
    if post.final_image_path and post.final_image_path.startswith(("http://", "https://")):
        return post.final_image_path
    return post.character.hero_image_url if post.character else None


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


async def _step_action(action):
    """Run a compute action (submit one step) and map its errors to HTTP."""
    try:
        return await action
    except steps.BusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except steps.CharacterRequired as e:  # before StepError, its parent
        raise ReasonedHTTPException(409, str(e), "character_required") from e
    except steps.StepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _active_step_view(post: Post) -> dict | None:
    active = steps.active_step(post)
    if active is None:
        return None
    return {"name": active["name"], "started_at": active.get("started_at"),
            "task": getattr(post, "active_task", None)}


def _serialize_post(post: Post) -> dict:
    backdrop_version = post.backdrop_version
    backdrop = post.scene_asset
    active_backdrop = backdrop if backdrop and backdrop.archived_at is None else None
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
        "scene_asset_display_name": (
            backdrop.display_name or backdrop.name.replace("_", " ").capitalize()
            if backdrop else None),
        "scene_asset_version": backdrop_version.version if backdrop_version else None,
        "scene_asset_latest_version": (
            active_backdrop.current_version if active_backdrop else None),
        "scene_asset_is_latest": bool(
            backdrop_version and active_backdrop
            and backdrop_version.version == active_backdrop.current_version),
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
        "image_profile": post.image_profile,
        "active_step": _active_step_view(post),
        "step_error": post.step_error,
        "can_retry_step": steps.can_retry(post),
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


def _idle_post_or_409(db: Session, post_id: str, user: AuthUser) -> Post:
    """Plain (non-compute) actions must not change a post mid-step."""
    post = _post_or_404(db, post_id, user)
    if post.active_step:
        raise HTTPException(status_code=409, detail=f"post {post_id} is busy with a step -- "
                            "wait for it to finish")
    return post


def _post_or_404(db: Session, post_id: str, user: AuthUser) -> Post:
    """Another owner's post is 404 too: nothing reveals what exists."""
    post = db.get(Post, post_id)
    if post is None or post.owner_id != user.id:
        raise HTTPException(status_code=404, detail=f"post {post_id} not found")
    return post


def _post_usage_summary(post: Post) -> dict:
    return {
        "id": post.id,
        "brief": post.brief,
        "status": post.status,
        "updated_at": _utc_iso(post.updated_at),
    }


def _serialize_scene_asset(asset: SceneAsset, db: Session) -> dict:
    usage = ps.scene_asset_usage_posts(db, asset.name, owner_id=asset.owner_id)
    return {
        "name": asset.name,
        "display_name": asset.display_name or asset.name.replace("_", " ").capitalize(),
        "detail_text": asset.detail_text,
        "current_version": asset.current_version,
        "archived_at": _utc_iso(asset.archived_at),
        "usage_count": len(usage),
        "created_at": _utc_iso(asset.created_at),
        "updated_at": _utc_iso(asset.updated_at),
    }


def _serialize_scene_asset_version(version: SceneAssetVersion, db: Session) -> dict:
    usage = ps.scene_asset_usage_posts(db, version.scene_asset_name, version.id,
                                       owner_id=version.owner_id)
    return {
        "id": version.id,
        "scene_asset_name": version.scene_asset_name,
        "version": version.version,
        "detail_text": version.detail_text,
        "usage_count": len(usage),
        "posts": [_post_usage_summary(post) for post in usage],
        "created_at": _utc_iso(version.created_at),
    }


def _json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serialize_character(character: Character) -> dict:
    return {
        "character_id": character.character_id,
        "display_name": character.display_name,
        "personality": character.personality,
        "character_card": _json_object(character.card_json),
        "hero_asset_id": character.hero_asset_id,
        "hero_candidate_id": character.hero_candidate_id,
        "hero_version": character.hero_version,
        "hero_image_url": character.hero_image_url,
        "updated_at": _utc_iso(character.updated_at),
    }


def _serialize_hero_candidate(candidate: HeroCandidate,
                              character: Character | None = None) -> dict:
    return {
        "id": candidate.id,
        "task_id": candidate.task_id,
        "seed": candidate.seed,
        "status": candidate.status,
        "image_url": candidate.image_url,
        "asset_id": candidate.asset_id,
        "metadata": _json_object(candidate.metadata_json),
        "error": candidate.error,
        "selected_at": _utc_iso(candidate.selected_at),
        "is_active_hero": bool(
            character and (
                character.hero_candidate_id == candidate.id
                or (not character.hero_candidate_id and candidate.asset_id
                    and character.hero_asset_id == candidate.asset_id))),
        "created_at": _utc_iso(candidate.created_at),
        "updated_at": _utc_iso(candidate.updated_at),
    }


def _serialize_hero_run(run: HeroGenerationRun) -> dict:
    return {
        "id": run.id,
        "character_id": run.character_id,
        "status": run.status,
        "profile": run.profile,
        "base_seed": run.base_seed,
        "requested_candidates": run.requested_candidates,
        "candidates": [_serialize_hero_candidate(candidate, run.character)
                       for candidate in run.candidates],
        "created_at": _utc_iso(run.created_at),
        "updated_at": _utc_iso(run.updated_at),
    }


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@public_router.get("/health")
def health():
    return {"status": "ok"}


@public_router.get("/auth/config")
def auth_config():
    return public_auth_config()


@router.get("/auth/me")
def auth_me(user: AuthUser = Depends(current_user)):
    return {"email": user.email, "user_id": user.id}


def _serialize_profile(profile) -> dict:
    return {"profile_md": profile.profile_md if profile else None,
            "is_set": profile is not None,
            "template": profile_service.template(),
            "updated_at": _utc_iso(profile.updated_at) if profile else None}


@router.get("/profile")
def get_writer_profile(db: Session = Depends(get_db),
                       user: AuthUser = Depends(current_user)):
    return _serialize_profile(profile_service.get_profile(db, user.id))


@router.put("/profile")
def put_writer_profile(req: WriterProfileRequest, db: Session = Depends(get_db),
                       user: AuthUser = Depends(current_user)):
    return _serialize_profile(profile_service.save_profile(db, user.id, req.profile_md))


@router.get("/resources/image-readiness")
async def get_image_readiness(client: httpx.AsyncClient = Depends(get_http_client)):
    return await hosted_image_readiness(client)


@router.get("/resources/renderer-status")
async def get_renderer_status(client: httpx.AsyncClient = Depends(get_http_client)):
    return await hosted_renderer_status(client)


@router.post("/characters", status_code=201)
def create_character(req: CharacterCardRequest,
                     db: Session = Depends(get_db),
                     user: AuthUser = Depends(current_user)):
    if db.get(Character, req.character_id) is not None:
        raise HTTPException(409, f"character {req.character_id!r} already exists")
    card = req.model_dump()
    character = Character(
        character_id=req.character_id,
        owner_id=user.id,
        display_name=req.display_name or None,
        personality=req.personality or None,
        card_json=json.dumps(card, separators=(",", ":"), sort_keys=True),
    )
    db.add(character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, f"character {req.character_id!r} already exists") from exc
    db.refresh(character)
    return _serialize_character(character)


def _character_or_404(db: Session, character_id: str, user: AuthUser) -> Character:
    """Another owner's character is 404 too: nothing reveals what exists."""
    character = db.get(Character, character_id)
    if character is None or character.owner_id != user.id:
        raise HTTPException(404, f"character {character_id!r} not found")
    return character


@router.get("/characters")
def list_characters(db: Session = Depends(get_db),
                    user: AuthUser = Depends(current_user)):
    characters = db.scalars(
        select(Character).where(Character.owner_id == user.id)
        .order_by(Character.character_id)).all()
    return [_serialize_character(character) for character in characters]


@router.get("/characters/{character_id}")
def get_character(character_id: str, db: Session = Depends(get_db),
                  user: AuthUser = Depends(current_user)):
    return _serialize_character(_character_or_404(db, character_id, user))


@router.post("/characters/{character_id}/hero-generations", status_code=202)
async def start_hero_generation(
        character_id: str, req: HeroGenerationRequest,
        db: Session = Depends(get_db),
        client: httpx.AsyncClient = Depends(get_http_client),
        user: AuthUser = Depends(current_user)):
    _character_or_404(db, character_id, user)
    seed = req.base_seed if req.base_seed is not None else secrets.randbelow(900_000) + 100_000
    try:
        run = await hgs.start_generation(
            db, client, character_id, req.candidate_count, seed, req.profile)
    except hgs.HeroGenerationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _serialize_hero_run(run)


@router.get("/characters/{character_id}/hero-generations")
def list_hero_generations(character_id: str, db: Session = Depends(get_db),
                          user: AuthUser = Depends(current_user)):
    _character_or_404(db, character_id, user)
    runs = db.scalars(
        select(HeroGenerationRun)
        .where(HeroGenerationRun.character_id == character_id)
        .order_by(HeroGenerationRun.created_at.desc())).all()
    return [_serialize_hero_run(run) for run in runs]


def _storage_auth(user: AuthUser) -> tuple[str, str] | None:
    """(bearer, apikey) for Supabase Storage uploads. Hosted (login on): the
    signed-in user's own session, allowed by the Storage policy from
    scripts/init_db.py -- no service key on the server. Local development
    without login falls back to SUPABASE_SERVICE_KEY when set."""
    if settings.auth_enabled:
        if not user.access_token:
            return None
        return user.access_token, settings.supabase_publishable_key
    if settings.supabase_service_key:
        return settings.supabase_service_key, settings.supabase_service_key
    return None


@router.get("/characters/{character_id}/hero-generations/{run_id}")
async def get_hero_generation(
        character_id: str, run_id: str,
        db: Session = Depends(get_db),
        client: httpx.AsyncClient = Depends(get_http_client),
        user: AuthUser = Depends(current_user)):
    _character_or_404(db, character_id, user)
    run = db.get(HeroGenerationRun, run_id)
    if run is None or run.character_id != character_id:
        raise HTTPException(404, f"hero generation {run_id!r} not found")
    async with hgs.storage_client() as storage:
        run = await hgs.advance_generation(
            db, client, run, storage_auth=_storage_auth(user), storage_client=storage)
    return _serialize_hero_run(run)


@router.post("/characters/{character_id}/hero-candidates/{candidate_id}/lock")
def lock_hero_candidate(character_id: str, candidate_id: str,
                        db: Session = Depends(get_db),
                        user: AuthUser = Depends(current_user)):
    _character_or_404(db, character_id, user)
    try:
        character, candidate = hgs.lock_candidate(db, character_id, candidate_id)
    except hgs.HeroGenerationNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except hgs.HeroCandidateNotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"character": _serialize_character(character),
            "candidate": _serialize_hero_candidate(candidate, character)}


@router.post("/posts")
async def create_post(req: CreatePostRequest, db: Session = Depends(get_db),
                      client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    # Compute actions only submit their first step and return at once; status
    # checks (GET) advance the post step by step -- see services/steps.py.
    if profile_service.get_profile(db, user.id) is None:
        raise ReasonedHTTPException(409, "Write your writer profile first", "profile_required")
    try:
        character_id = choose_character(db, owner_id=user.id, requested=req.character_id)
    except CharacterNotOwned as e:
        raise HTTPException(404, str(e)) from e
    except MascotRequired as e:
        raise ReasonedHTTPException(409, str(e), "character_required") from e
    post = await _step_action(steps.start_create(
        db, client, req.brief, character_id, owner_id=user.id))
    return _serialize_post(post)


@router.get("/posts")
async def list_posts(db: Session = Depends(get_db),
                     client: httpx.AsyncClient = Depends(get_http_client),
        user: AuthUser = Depends(current_user)):
    posts = []
    for p in ps.list_posts(db, owner_id=user.id):
        try:
            p = await steps.advance(db, client, p)
        except Exception:  # noqa: BLE001 -- one bad post must not hide the list
            db.rollback()
        posts.append(p)
    return [_serialize_post(p) for p in posts]


@router.get("/posts/{post_id}")
async def get_post(post_id: str, db: Session = Depends(get_db),
                   client: httpx.AsyncClient = Depends(get_http_client),
        user: AuthUser = Depends(current_user)):
    post = await steps.advance(db, client, _post_or_404(db, post_id, user))
    return _serialize_post(post)


@router.post("/posts/{post_id}/clarify")
async def clarify(post_id: str, req: ClarifyRequest, db: Session = Depends(get_db),
                  client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(
        steps.start_clarify_answer(db, client, post_id, req.answer)))


@router.post("/posts/{post_id}/additional-info")
async def additional_info(post_id: str, req: AdditionalInfoRequest, db: Session = Depends(get_db),
                          client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    """Human's response to a needs_input escalation -- unbounded, unlike the
    automatic recalibration loop."""
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(
        steps.start_additional_info(db, client, post_id, req.info)))


@router.post("/posts/{post_id}/accept-draft")
def accept_draft(post_id: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    """Human's call to proceed with the current best draft despite an
    escalation notice -- the human is always the final gate."""
    _idle_post_or_409(db, post_id, user)
    try:
        post = ps.accept_current_draft(db, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/draft")
async def redraft(post_id: str, db: Session = Depends(get_db),
                  client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(steps.start_redraft(db, client, post_id)))


@router.post("/posts/{post_id}/regenerate")
async def regenerate(post_id: str, req: RegenerateRequest, db: Session = Depends(get_db),
                     client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(
        steps.start_regenerate(db, client, post_id, req.instruction)))


@router.get("/posts/{post_id}/drafts")
def get_drafts(post_id: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return [_serialize_draft(d) for d in ps.list_drafts(db, post_id)]


@router.post("/posts/{post_id}/feedback")
def add_feedback(post_id: str, req: FeedbackRequest, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    fb = fs.create_feedback(db, post_id, req.stage, req.user_note, req.post_text_snippet)
    return _serialize_feedback(fb)


@router.get("/posts/{post_id}/feedback")
def get_feedback(post_id: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return [_serialize_feedback(fb) for fb in fs.list_feedback(db, post_id)]


@router.post("/posts/{post_id}/lock")
async def lock(post_id: str, db: Session = Depends(get_db),
               client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(steps.start_lock(db, client, post_id)))


@router.patch("/posts/{post_id}/scene")
def update_scene(post_id: str, req: SceneUpdateRequest, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _idle_post_or_409(db, post_id, user)
    try:
        post = ps.update_scene(db, post_id, req.scene_instruction)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.patch("/posts/{post_id}/backdrop")
def set_post_backdrop(post_id: str, req: PostBackdropRequest, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _idle_post_or_409(db, post_id, user)
    try:
        post = ps.set_post_scene_asset(db, post_id, req.scene_asset_name)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.patch("/posts/{post_id}/character")
def set_post_character(post_id: str, req: PostCharacterRequest, db: Session = Depends(get_db),
                       user: AuthUser = Depends(current_user)):
    """Pick the character for a post's image (one of the owner's, with a
    locked hero). A rendered image no longer matches, so it needs a fresh one."""
    post = _idle_post_or_409(db, post_id, user)
    if post.status == "ready":
        raise HTTPException(400, f"post {post_id} is finished")
    if post.status == "image_queued":
        raise HTTPException(409, f"post {post_id} is rendering -- wait for the image to finish")
    character = _character_or_404(db, req.character_id, user)
    if not character.hero_image_url:
        raise ReasonedHTTPException(
            409, f"character {req.character_id!r} has no locked hero yet", "character_required")
    if post.character_id != character.character_id:
        post.character_id = character.character_id
        if post.status in ("image_ready", "image_failed"):
            post.status = "locked"
            post.image_job_error = None
        db.commit()
        db.refresh(post)
    return _serialize_post(post)


@router.post("/posts/{post_id}/scene/use-latest-backdrop")
def use_latest_backdrop(post_id: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _idle_post_or_409(db, post_id, user)
    try:
        post = ps.use_latest_scene_asset(db, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.post("/posts/{post_id}/generate-image")
async def generate_image(post_id: str, req: GenerateImageRequest | None = None,
                         db: Session = Depends(get_db),
                         client: httpx.AsyncClient = Depends(get_http_client),
        user: AuthUser = Depends(current_user)):
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(
        steps.start_image(db, client, post_id, profile=req.profile if req else "full")))


@router.post("/posts/{post_id}/retry-step")
async def retry_step(post_id: str, db: Session = Depends(get_db),
                     client: httpx.AsyncClient = Depends(get_llm_client),
        user: AuthUser = Depends(current_user)):
    """Resubmit the step that failed -- the user's call, never automatic."""
    _post_or_404(db, post_id, user)
    return _serialize_post(await _step_action(steps.retry_step(db, client, post_id)))


@router.post("/posts/{post_id}/finalize")
def finalize(post_id: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    _idle_post_or_409(db, post_id, user)
    try:
        post = ps.finalize_post(db, post_id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_post(post)


@router.get("/scene-assets")
def list_scene_assets(include_archived: bool = False, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    return [
        _serialize_scene_asset(asset, db)
        for asset in ps.list_scene_assets(db, owner_id=user.id, include_archived=include_archived)
    ]


@router.post("/scene-assets", status_code=201)
def create_scene_asset(req: SceneAssetCreateRequest, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    try:
        asset = ps.create_scene_asset(db, req.display_name, req.detail_text, owner_id=user.id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_scene_asset(asset, db)


@router.patch("/scene-assets/{name}")
def update_scene_asset(name: str, req: SceneAssetUpdateRequest, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    try:
        asset = ps.update_scene_asset(db, name, req.detail_text, req.display_name,
                                      owner_id=user.id)
    except ps.SceneAssetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ps.PostServiceError as e:  # validation: empty description / name
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_scene_asset(asset, db)


@router.get("/scene-assets/{name}/versions")
def list_scene_asset_versions(name: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    return [
        _serialize_scene_asset_version(version, db)
        for version in ps.list_scene_asset_versions(db, name, owner_id=user.id)
    ]


@router.post("/scene-assets/{name}/versions/{version}/restore")
def restore_scene_asset_version(name: str, version: int, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    try:
        asset = ps.restore_scene_asset_version(db, name, version, owner_id=user.id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_scene_asset(asset, db)


@router.post("/scene-assets/{name}/archive")
def archive_scene_asset(name: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    try:
        asset = ps.archive_scene_asset(db, name, owner_id=user.id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_scene_asset(asset, db)


@router.post("/scene-assets/{name}/unarchive")
def unarchive_scene_asset(name: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    try:
        asset = ps.unarchive_scene_asset(db, name, owner_id=user.id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_scene_asset(asset, db)


@router.delete("/scene-assets/{name}")
def delete_scene_asset(name: str, db: Session = Depends(get_db),
        user: AuthUser = Depends(current_user)):
    """Backward-compatible archive behavior for older clients."""
    try:
        ps.delete_scene_asset(db, name, owner_id=user.id)
    except ps.PostServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "archived"}
