import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from .database import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = Column(String, nullable=False, default="gtee_dev")
    brief = Column(Text, nullable=False)
    clarify_transcript = Column(Text, nullable=True)  # JSON-encoded list of turns

    # clarifying|needs_input|drafting|locked|image_queued|image_ready|image_failed|ready
    # needs_input: an escalation from the recalibration loop that a rewrite
    # can't fix (needs new material or a different angle) -- see
    # CONTENT_QUALITY_DESIGN.md and post_service.py's _draft_and_score().
    status = Column(String, nullable=False, default="clarifying")

    post_text = Column(Text, nullable=True)
    draft_version = Column(Integer, nullable=False, default=0)

    # content-quality scoring (see taxonomy.py / judge_agent.py). category is
    # inferred once during clarify and reused for pillar weighting at every
    # subsequent score. gate_scores/pillar_scores are JSON-encoded
    # {pillar: {"score": float, "reason": str}}. escalation_reason is set only
    # while status == "needs_input", cleared once resolved.
    category = Column(String, nullable=True)
    gate_scores = Column(Text, nullable=True)
    pillar_scores = Column(Text, nullable=True)
    weighted_score = Column(Float, nullable=True)
    recalibration_count = Column(Integer, nullable=False, default=0)
    escalation_reason = Column(Text, nullable=True)

    scene_instruction = Column(Text, nullable=True)
    # Name of the SceneAsset (recurring backdrop, e.g. "office") this post's
    # scene reused/created, if any -- null for one-off metaphor scenes with
    # no reusable setting. Traceability only; the asset's own detail_text is
    # the source of truth, this just lets the UI point back to it.
    scene_asset_name = Column(String, nullable=True)
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


class SceneAsset(Base):
    """A recurring, named visual backdrop (e.g. "office", "coffee_shop") --
    text-only, name -> detail-text mapping, per the explicit design decision
    that this is NOT reference-image-based consistency (see
    linkedin-content-agent-product-pivot memory note / this session's
    brainstorm). Grows dynamically: scene_agent proposes a name for any scene
    whose backdrop is a real recurring place (not a one-off metaphor prop);
    if the name is new, whatever detail text it generated this time becomes
    the seed, persisted here for every future scene with that name to reuse
    verbatim instead of re-deriving generic phrasing each time."""
    __tablename__ = "scene_assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)  # slug, e.g. "office"
    detail_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    stage = Column(String, nullable=False)  # draft|image_scene|final
    post_text_snippet = Column(Text, nullable=True)
    user_note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
