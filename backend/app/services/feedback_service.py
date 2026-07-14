"""Feedback capture -- create/list only.

No consumption or few-shot injection into draft/scene prompts here. Different
post types (technical write-up vs. quick update vs. commentary) will need
different feedback semantics, and that taxonomy doesn't exist yet -- ship
capture, observe what real feedback looks like, design consumption later.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Feedback


def create_feedback(db: Session, post_id: str, stage: str, user_note: str,
                    post_text_snippet: str | None = None) -> Feedback:
    fb = Feedback(post_id=post_id, stage=stage, user_note=user_note,
                 post_text_snippet=post_text_snippet)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def list_feedback(db: Session, post_id: str) -> list[Feedback]:
    return (db.query(Feedback)
            .filter(Feedback.post_id == post_id)
            .order_by(Feedback.created_at.asc())
            .all())
