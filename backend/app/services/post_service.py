"""post_service.py -- orchestrates the Post state machine.

clarifying -> drafting -> locked -> image_queued -> image_ready|image_failed -> ready

Clarify transcript is stored as a JSON list of {"question", "answer"} on
Post.clarify_transcript. A pending (unanswered) question is represented as
the last entry with answer=None; only fully-answered turns are ever passed
to draft_agent (see _answered_turns).

image_queued/image_ready/image_failed/ready transitions live in
image_service.py, not here -- this module only goes as far as "locked".
"""
from __future__ import annotations

import json
import random

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Post, PostDraft
from ..agents.draft_agent import clarify_turn, generate_draft, regenerate_draft
from ..agents.scene_agent import derive_scene


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


async def _advance_clarify(db: Session, client: httpx.AsyncClient, post: Post,
                           answered: list[dict]) -> Post:
    result = await clarify_turn(client, post.brief, answered)

    # Cap: force done once we've already asked clarify_max_turns questions,
    # regardless of what the model wants -- a thin brief stays thin rather
    # than looping forever asking for detail that isn't coming.
    if not result["done"] and len(answered) >= settings.clarify_max_turns:
        result = {"done": True, "question": None}

    if result["done"]:
        _save_transcript(post, answered)
        draft_text = await generate_draft(client, post.brief, answered)
        version = 1
        db.add(PostDraft(post_id=post.id, version=version, post_text=draft_text,
                         generated_by="draft", user_instruction=None))
        post.post_text = draft_text
        post.draft_version = version
        post.status = "drafting"
    else:
        transcript = answered + [{"question": result["question"], "answer": None}]
        _save_transcript(post, transcript)
        # status stays "clarifying"

    db.commit()
    db.refresh(post)
    return post


async def create_post(db: Session, client: httpx.AsyncClient, brief: str,
                      character_id: str | None = None) -> Post:
    post = Post(character_id=character_id or settings.default_character_id,
               brief=brief, status="clarifying", clarify_transcript=json.dumps([]))
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


async def redraft_post(db: Session, client: httpx.AsyncClient, post_id: str) -> Post:
    """Fresh draft from the original brief + clarification, discarding the
    current text -- a "start over" action distinct from regenerate's
    instruction-based revision of the existing draft."""
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    transcript = _answered_turns(_load_transcript(post))
    new_text = await generate_draft(client, post.brief, transcript)
    version = post.draft_version + 1
    db.add(PostDraft(post_id=post.id, version=version, post_text=new_text,
                     generated_by="draft", user_instruction=None))
    post.post_text = new_text
    post.draft_version = version
    db.commit()
    db.refresh(post)
    return post


async def regenerate_post_draft(db: Session, client: httpx.AsyncClient, post_id: str,
                                instruction: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    new_text = await regenerate_draft(client, post.post_text, instruction)
    version = post.draft_version + 1
    db.add(PostDraft(post_id=post.id, version=version, post_text=new_text,
                     generated_by="regenerate", user_instruction=instruction))
    post.post_text = new_text
    post.draft_version = version
    db.commit()
    db.refresh(post)
    return post


async def lock_post(db: Session, client: httpx.AsyncClient, post_id: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "drafting":
        raise PostServiceError(f"post {post_id} is not in drafting state "
                               f"(status={post.status})")
    scene = await derive_scene(client, post.post_text)
    post.scene_instruction = scene
    post.seed = random.randint(1, 999_999)
    post.status = "locked"
    db.commit()
    db.refresh(post)
    return post


def update_scene(db: Session, post_id: str, scene_instruction: str) -> Post:
    """Let the user edit the derived scene before triggering the real (15-20
    min) render -- only while locked and before image generation has started."""
    post = get_post(db, post_id)
    if post.status != "locked":
        raise PostServiceError(f"post {post_id} is not locked (status={post.status})")
    post.scene_instruction = scene_instruction
    db.commit()
    db.refresh(post)
    return post


def finalize_post(db: Session, post_id: str) -> Post:
    post = get_post(db, post_id)
    if post.status != "image_ready":
        raise PostServiceError(f"post {post_id} has no ready image "
                               f"(status={post.status})")
    post.status = "ready"
    db.commit()
    db.refresh(post)
    return post
