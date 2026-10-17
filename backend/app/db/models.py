import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (Index("ix_posts_owner_created", "owner_id", "created_at"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Supabase user id of the post's owner ("auth-disabled" locally).
    owner_id = Column(String, nullable=False)
    # The owner's mascot used for the image; null until one is chosen (text
    # steps work without it).
    character_id = Column(String, nullable=True)
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
    recalibration_count = Column(Integer, nullable=False, default=0, server_default="0")
    escalation_reason = Column(Text, nullable=True)

    scene_instruction = Column(Text, nullable=True)
    # Name of the SceneAsset (recurring backdrop, e.g. "office") this post's
    # scene reused/created, if any -- null for one-off metaphor scenes with
    # no reusable setting. The name keeps the prompt readable and lets the UI
    # point back to the active asset; scene_asset_version_id is the immutable
    # source of truth for this post.
    scene_asset_name = Column(String, nullable=True)
    # Immutable SceneAssetVersion pinned when this scene was created or the
    # user explicitly chose a backdrop. The short @name stays readable while
    # this id preserves the exact historical meaning used at render time.
    scene_asset_version_id = Column(String, ForeignKey("scene_asset_versions.id"), nullable=True)
    seed = Column(Integer, nullable=True)
    # The rendered image's Supabase Storage URL (via the task-queue's
    # artifact store). Very old rows may hold a local file path, which is no
    # longer served -- _image_url() in routes.py shows the placeholder.
    final_image_path = Column(String, nullable=True)
    image_job_error = Column(Text, nullable=True)
    # id of the task-queue task tracking this post's in-flight/most-recent
    # image generation request -- the step engine's `image` step (services/steps.py).
    image_task_id = Column(String, nullable=True)
    # full | lightning, as last requested by the user -- Retry reuses it.
    image_profile = Column(String, nullable=True)
    # Phase 3a step engine (see services/steps.py). active_step: JSON
    # {name, task_id, started_at} of the one in-flight queue task, NULL when
    # idle. step_context: JSON carried between steps (attempt count, ...).
    # step_error: last failed step's message, shown with "Retry step".
    active_step = Column(Text, nullable=True)
    step_context = Column(Text, nullable=True)
    step_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    image_started_at = Column(DateTime, nullable=True)  # stall-detection anchor

    # The mascot (personality, placeholder image). No foreign key: a post
    # whose mascot has no row yet still works, just without them.
    character = relationship(
        "Character", primaryjoin="foreign(Post.character_id) == Character.character_id",
        viewonly=True, lazy="selectin")
    # Joined on the owner too: two users may each have an "office".
    scene_asset = relationship(
        "SceneAsset",
        primaryjoin="and_(foreign(Post.scene_asset_name) == SceneAsset.name, "
                    "foreign(Post.owner_id) == SceneAsset.owner_id)",
        viewonly=True, lazy="selectin")
    backdrop_version = relationship(
        "SceneAssetVersion", foreign_keys=[scene_asset_version_id],
        viewonly=True, lazy="selectin")


class Character(Base):
    """The brand mascot, copied from character-forge-v2 by
    scripts/sync_character.py or made in Character Studio. owner_id is the
    Supabase user id of its owner; character_id stays globally unique."""
    __tablename__ = "characters"

    character_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    personality = Column(Text, nullable=True)
    # Complete provider-neutral CharacterCard JSON. Workers receive a
    # snapshot with each render, so they do not need this app's database or a
    # matching character-forge workspace checkout.
    card_json = Column(Text, nullable=True)
    # Content-addressed identity of the selected hero. The URL is only a
    # locator and may change; workers cache by asset id + version.
    hero_asset_id = Column(String, nullable=True)
    hero_version = Column(Integer, nullable=False, default=0)
    hero_image_url = Column(String, nullable=True)  # public Storage URL, ?v=<content hash>
    # Exact selected candidate, kept separate from asset identity because two
    # seeds can legitimately produce byte-identical images. Null for legacy
    # heroes imported directly from a Character Forge workspace.
    hero_candidate_id = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class HeroGenerationRun(Base):
    """One request for several independently queued hero candidates."""
    __tablename__ = "hero_generation_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = Column(String, ForeignKey("characters.character_id"), nullable=False)
    # Snapshot used for every candidate in the run. Later CharacterCard edits
    # cannot make an old run impossible to reproduce or explain.
    card_json = Column(Text, nullable=False)
    profile = Column(String, nullable=False)
    base_seed = Column(Integer, nullable=False)
    requested_candidates = Column(Integer, nullable=False)
    # submitting|running|completed|partial_failed|failed
    status = Column(String, nullable=False, default="submitting")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    character = relationship("Character", lazy="selectin")
    candidates = relationship(
        "HeroCandidate", back_populates="run", cascade="all, delete-orphan",
        order_by="HeroCandidate.seed", lazy="selectin")


class HeroCandidate(Base):
    """A single queue task and its promoted, durable image asset."""
    __tablename__ = "hero_candidates"
    __table_args__ = (UniqueConstraint("run_id", "seed", name="uq_hero_candidate_run_seed"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("hero_generation_runs.id"), nullable=False)
    task_id = Column(String, nullable=True, unique=True)
    seed = Column(Integer, nullable=False)
    # submitting|queued|claimed|promotion_failed|ready|failed
    status = Column(String, nullable=False, default="submitting")
    queue_artifact_id = Column(String, nullable=True)
    asset_id = Column(String, nullable=True)  # sha256:<hex> of durable bytes
    storage_path = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    selected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    run = relationship("HeroGenerationRun", back_populates="candidates")


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
    the seed. detail_text/current_version point to the active revision;
    immutable SceneAssetVersion rows preserve what older posts used."""
    __tablename__ = "scene_assets"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_scene_asset_owner_name"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)
    name = Column(String, nullable=False)  # slug, e.g. "office"; unique per owner
    # Editable label for people; `name` stays the stable prompt identifier.
    display_name = Column(String, nullable=True)
    detail_text = Column(Text, nullable=False)
    current_version = Column(Integer, nullable=False, default=1, server_default="1")
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SceneAssetVersion(Base):
    """An immutable revision of a recurring backdrop description.

    The name deliberately is not a foreign key to SceneAsset: archiving an
    active backdrop must not destroy history pinned by older posts.
    """
    __tablename__ = "scene_asset_versions"
    __table_args__ = (
        UniqueConstraint("owner_id", "scene_asset_name", "version",
                         name="uq_scene_asset_version_owner"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)
    scene_asset_name = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    detail_text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    stage = Column(String, nullable=False)  # draft|image_scene|final
    post_text_snippet = Column(Text, nullable=True)
    user_note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WriterProfile(Base):
    """Who the writer is (Markdown, at most 8,000 characters): one per user.
    Replaces content_config/user_profile.md, which stays as the template."""
    __tablename__ = "writer_profiles"

    owner_id = Column(String, primary_key=True)
    profile_md = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
