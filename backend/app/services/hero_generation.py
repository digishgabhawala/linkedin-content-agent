"""Durable hero-candidate generation on top of the generic Task Queue.

One run owns N candidates, and every candidate owns one queue task. Queue
artifacts are transport objects with finite retention; when a task finishes,
``advance_generation`` copies its image into this app's durable Supabase
Storage namespace before marking the candidate ready.

HTTP routes and the Character Studio UI intentionally sit above this module
and are a later slice. Keeping orchestration here makes those routes thin and
lets the lifecycle be tested without a real queue, GPU, or Supabase project.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Character, HeroCandidate, HeroGenerationRun
from . import llm_client

TERMINAL_CANDIDATE_STATUSES = frozenset({"ready", "failed"})
VALID_PROFILES = frozenset({"full", "lightning"})
MAX_CANDIDATES_PER_RUN = 12


class HeroGenerationError(Exception):
    pass


class HeroGenerationNotFound(HeroGenerationError):
    pass


class HeroCandidateNotReady(HeroGenerationError):
    pass


def _character_card(character: Character) -> dict:
    try:
        card = json.loads(character.card_json or "")
    except (TypeError, json.JSONDecodeError) as exc:
        raise HeroGenerationError(
            f"character {character.character_id!r} has no valid CharacterCard") from exc
    if not isinstance(card, dict) or card.get("character_id") != character.character_id:
        raise HeroGenerationError(
            f"character {character.character_id!r} has a mismatched CharacterCard")
    return card


def _validate_request(candidate_count: int, base_seed: int, profile: str) -> None:
    if not 1 <= candidate_count <= MAX_CANDIDATES_PER_RUN:
        raise HeroGenerationError(
            f"candidate_count must be between 1 and {MAX_CANDIDATES_PER_RUN}")
    if type(base_seed) is not int:
        raise HeroGenerationError("base_seed must be an integer")
    if profile not in VALID_PROFILES:
        raise HeroGenerationError(f"unsupported image profile: {profile!r}")


def _refresh_run_status(run: HeroGenerationRun) -> None:
    statuses = {candidate.status for candidate in run.candidates}
    if statuses == {"ready"}:
        run.status = "completed"
    elif statuses == {"failed"}:
        run.status = "failed"
    elif statuses <= TERMINAL_CANDIDATE_STATUSES:
        run.status = "partial_failed"
    elif statuses:
        run.status = "running"
    else:
        run.status = "submitting"


async def start_generation(db: Session, client: httpx.AsyncClient,
                           character_id: str, candidate_count: int,
                           base_seed: int, profile: str = "full") -> HeroGenerationRun:
    """Persist a run, then submit one isolated task for each candidate."""
    _validate_request(candidate_count, base_seed, profile)
    character = db.get(Character, character_id)
    if character is None:
        raise HeroGenerationError(f"character {character_id!r} not found")
    card = _character_card(character)
    card_json = json.dumps(card, separators=(",", ":"), sort_keys=True)
    run = HeroGenerationRun(
        character_id=character_id,
        card_json=card_json,
        profile=profile,
        base_seed=base_seed,
        requested_candidates=candidate_count,
        candidates=[HeroCandidate(seed=base_seed + index)
                    for index in range(candidate_count)],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    unavailable_error = None
    for candidate in run.candidates:
        if unavailable_error is not None:
            candidate.status = "failed"
            candidate.error = unavailable_error
            continue
        try:
            candidate.task_id = await llm_client.submit_hero_candidate(
                client, card, candidate.seed, profile)
            candidate.status = "queued"
        except llm_client.TaskQueueUnavailable as exc:
            # Stop hammering an unavailable queue. The persisted run makes
            # the failure visible and a later API can offer explicit retry.
            unavailable_error = str(exc)
            candidate.status = "failed"
            candidate.error = unavailable_error
    _refresh_run_status(run)
    db.commit()
    db.refresh(run)
    return run


def storage_client() -> httpx.AsyncClient:
    """A plain client for Supabase Storage. Never the task-queue client: that
    one carries this app's queue key (X-API-Key) on every request."""
    return httpx.AsyncClient(timeout=60)


class ArtifactExpired(HeroGenerationError):
    """The queue's temporary copy is gone (finite retention); retrying the
    promotion can never succeed, so the candidate fails for good."""


async def _promote_artifact(storage: httpx.AsyncClient,
                            storage_auth: tuple[str, str] | None,
                            run: HeroGenerationRun, candidate: HeroCandidate,
                            artifact_url: str) -> tuple[str, str, str]:
    if not settings.supabase_url or storage_auth is None:
        raise HeroGenerationError(
            "no Storage credential to promote hero candidates (sign in, or set "
            "SUPABASE_URL and SUPABASE_SERVICE_KEY for local development)")
    response = await storage.get(artifact_url, timeout=60)
    if response.status_code in (400, 404):  # Storage reports a missing object as either
        raise ArtifactExpired("the queue's copy of this candidate image has expired")
    response.raise_for_status()
    image = response.content
    if not image:
        raise HeroGenerationError("queue artifact was empty")
    digest = hashlib.sha256(image).hexdigest()
    asset_id = f"sha256:{digest}"
    storage_path = (
        f"characters/{run.character_id}/candidates/{candidate.id}.png")
    base = settings.supabase_url.rstrip("/")
    bearer, apikey = storage_auth
    upload = await storage.post(
        f"{base}/storage/v1/object/{settings.storage_bucket}/{storage_path}",
        headers={"Authorization": f"Bearer {bearer}", "apikey": apikey,
                 "Content-Type": "image/png", "x-upsert": "true"},
        content=image,
        timeout=60,
    )
    if upload.status_code not in (200, 201):
        raise HeroGenerationError(
            f"promoting candidate failed: {upload.status_code} {upload.text}")
    public_url = (
        f"{base}/storage/v1/object/public/{settings.storage_bucket}/{storage_path}"
        f"?v={digest[:16]}")
    return asset_id, storage_path, public_url


async def advance_generation(db: Session, client: httpx.AsyncClient,
                             run: HeroGenerationRun, *,
                             storage_auth: tuple[str, str] | None,
                             storage_client: httpx.AsyncClient) -> HeroGenerationRun:
    """Poll unfinished tasks and durably promote every completed image.

    ``client`` talks to the task-queue; ``storage_client`` to Supabase Storage
    with ``storage_auth`` = (bearer token, apikey) -- the signed-in user's
    session when login is on, so the hosted app needs no service key."""
    for candidate in run.candidates:
        if candidate.status in TERMINAL_CANDIDATE_STATUSES or not candidate.task_id:
            continue
        try:
            task = await llm_client.get_task(client, candidate.task_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                candidate.status = "failed"
                candidate.error = "lost: candidate task is no longer in the queue"
            continue
        except httpx.HTTPError:
            continue

        task_status = task.get("status")
        if task_status in ("queued", "claimed"):
            candidate.status = task_status
            continue
        if task_status == "failed":
            candidate.status = "failed"
            candidate.error = task.get("error") or "hero candidate generation failed"
            continue
        if task_status != "done":
            continue

        try:
            result = task.get("result") or {}
            artifact_id = result["hero_candidate_artifact_id"]
            if not isinstance(artifact_id, str) or not artifact_id:
                raise HeroGenerationError("candidate artifact id is missing")
            metadata = result.get("candidate") or {}
            if not isinstance(metadata, dict):
                raise HeroGenerationError("candidate metadata is not an object")
        except (KeyError, HeroGenerationError) as exc:
            candidate.status = "failed"
            candidate.error = f"invalid candidate result: {exc}"
            continue

        try:
            try:
                artifact = await llm_client.get_artifact(client, artifact_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise ArtifactExpired("the queue no longer has this candidate image") from exc
                raise
            asset_id, storage_path, image_url = await _promote_artifact(
                storage_client, storage_auth, run, candidate, artifact["url"])
        except ArtifactExpired as exc:
            candidate.status = "failed"
            candidate.error = f"expired: {exc}; generate new candidates"
            continue
        except Exception as exc:  # noqa: BLE001 -- persisted and retried on the next poll
            # Queue results live for 48 hours, so a missing credential or
            # transient Storage outage should remain retryable. A later poll
            # repeats the idempotent upload to the same candidate path.
            candidate.status = "promotion_failed"
            candidate.error = f"could not promote candidate: {exc}"
            continue

        candidate.status = "ready"
        candidate.queue_artifact_id = artifact_id
        candidate.asset_id = asset_id
        candidate.storage_path = storage_path
        candidate.image_url = image_url
        candidate.metadata_json = json.dumps(
            metadata, separators=(",", ":"), sort_keys=True)
        candidate.error = None

    _refresh_run_status(run)
    db.commit()
    db.refresh(run)
    return run


def lock_candidate(db: Session, character_id: str,
                   candidate_id: str) -> tuple[Character, HeroCandidate]:
    """Atomically make a ready candidate the character's locked reference.

    The CharacterCard snapshot used to generate the candidate moves with the
    image, preventing a later edit from pairing an old candidate with a
    different identity prompt. Re-locking the active candidate is idempotent.
    """
    character = db.execute(
        select(Character).where(Character.character_id == character_id)
        .with_for_update()).scalar_one_or_none()
    if character is None:
        raise HeroGenerationNotFound(f"character {character_id!r} not found")
    candidate = db.execute(
        select(HeroCandidate)
        .join(HeroGenerationRun)
        .where(HeroCandidate.id == candidate_id,
               HeroGenerationRun.character_id == character_id)
        .with_for_update()).scalar_one_or_none()
    if candidate is None:
        raise HeroGenerationNotFound(
            f"hero candidate {candidate_id!r} not found for character {character_id!r}")
    if (candidate.status != "ready" or not candidate.asset_id
            or not candidate.image_url):
        raise HeroCandidateNotReady(
            f"hero candidate {candidate_id!r} is not ready to lock")

    if character.hero_asset_id != candidate.asset_id:
        character.hero_version = (character.hero_version or 0) + 1
    character.hero_asset_id = candidate.asset_id
    character.hero_image_url = candidate.image_url
    character.hero_candidate_id = candidate.id
    character.card_json = candidate.run.card_json
    card = json.loads(candidate.run.card_json)
    character.display_name = card.get("display_name")
    character.personality = card.get("personality")
    character.updated_at = datetime.utcnow()
    candidate.selected_at = candidate.selected_at or datetime.utcnow()
    db.commit()
    db.refresh(character)
    db.refresh(candidate)
    return character, candidate
