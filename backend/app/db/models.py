import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from .database import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = Column(String, nullable=False, default="gtee_dev")
    brief = Column(Text, nullable=False)
    clarify_transcript = Column(Text, nullable=True)  # JSON-encoded list of turns

    # clarifying|drafting|locked|image_queued|image_ready|image_failed|ready
    status = Column(String, nullable=False, default="clarifying")

    post_text = Column(Text, nullable=True)
    draft_version = Column(Integer, nullable=False, default=0)

    scene_instruction = Column(Text, nullable=True)
    seed = Column(Integer, nullable=True)
    final_image_path = Column(String, nullable=True)
    image_job_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    image_started_at = Column(DateTime, nullable=True)  # stall-detection anchor


class PostDraft(Base):
    __tablename__ = "post_drafts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    version = Column(Integer, nullable=False)
    post_text = Column(Text, nullable=False)
    generated_by = Column(String, nullable=False)  # draft|regenerate|user_edit
    user_instruction = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    stage = Column(String, nullable=False)  # draft|image_scene|final
    post_text_snippet = Column(Text, nullable=True)
    user_note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
