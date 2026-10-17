
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# backend/ -- content_config paths resolve from here, not from the working
# folder (a hosted function doesn't start in backend/).
_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # Where the app's data lives -- configuration, never hardcoded. Any
    # SQLAlchemy URL (e.g. the Supabase pooler,
    # postgresql+psycopg://...); unset means the local SQLite file at db_path.
    database_url: str | None = None
    # Postgres schema holding this app's tables (keeps them apart from other
    # apps sharing the same Supabase project). Ignored for SQLite.
    db_schema: str = "linkedin"
    db_path: str = "posts.db"  # SQLite fallback only
    # Create/upgrade tables on startup. Convenient locally; hosted (serverless)
    # sets false so a fresh function doesn't run schema checks on every start
    # -- run scripts/init_db.py before a deploy that changes the schema.
    auto_init_db: bool = True
    # The built frontend (npm run build), served by this app next to the API
    # -- one deployment, one origin. Skipped when the folder doesn't exist
    # (local development uses the Vite dev server instead).
    frontend_dist: str = str(_BACKEND_DIR.parent / "frontend" / "dist")

    default_character_id: str = "gtee_dev"
    clarify_max_turns: int = 5
    max_recalibration_passes: int = 3

    # WHO (user_profile.md) / HOW (skill.md) config -- see CONTENT_QUALITY_DESIGN.md.
    user_profile_path: str = str(_BACKEND_DIR / "content_config/user_profile.md")
    skill_path: str = str(_BACKEND_DIR / "content_config/skill.md")
    example_posts_path: str = str(_BACKEND_DIR / "content_config/example_posts.md")
    scene_examples_path: str = str(_BACKEND_DIR / "content_config/scene_examples.md")

    task_queue_url: str = "http://127.0.0.1:8000"
    # This app's machine key for the task-queue (sent as X-API-Key). Its
    # sha256 is registered in task-queue's SERVICE_API_KEYS.
    task_queue_api_key: str | None = None
    # Max minutes a queued step (LLM or image) may wait for a worker before
    # the worker discards it as expired; the user can then retry the step.
    step_max_wait_minutes: float = 60
    image_stall_timeout_minutes: int = 40

    # Login (same approach as task-queue's admin page): a Supabase session
    # whose platform profile is approved with a linkedin membership. Off by default so local development
    # and tests need no login; production sets AUTH_ENABLED=true.
    auth_enabled: bool = False
    supabase_url: str = ""
    supabase_publishable_key: str = ""  # browser-safe; also verifies tokens
    # LOCAL DEVELOPMENT ONLY (login off): lets hero candidates be copied into
    # Storage without a signed-in user. Hosted, uploads use the user's own
    # session (Storage policy in scripts/init_db.py) and this stays unset --
    # it bypasses every Supabase protection. Never expose it to the frontend.
    supabase_service_key: str = ""
    storage_bucket: str = "linkedin"
    # Migration only (scripts/init_db.py): the platform account (email in
    # platform.profiles) that owns rows created before multi-user. Needed
    # only while rows without an owner exist.
    backfill_owner_email: str = ""
    # How long a verified token is trusted before Supabase is asked again
    # (never past the token's own expiry). The UI polls every few seconds.
    auth_cache_minutes: float = 15
    # How long an account's approval status + linkedin membership (read from
    # the platform schema) is trusted. At most 60 s: a suspension must bite
    # within a minute.
    access_cache_seconds: float = 60

    class Config:
        env_file = ".env"
        # Retired keys (e.g. OLLAMA_URL/OLLAMA_MODEL -- text generation now
        # runs on the task-queue worker) must not stop the app starting.
        extra = "ignore"

    @property
    def task_queue_api_url(self) -> str:
        """Resolve the canonical suite page to the queue's scoped API.

        ``TASK_QUEUE_URL`` intentionally contains the public product URL so
        links, logs, notebooks, and deployments share one canonical address.
        Direct service origins and explicit API bases remain compatible.
        """
        normalized = self.task_queue_url.rstrip("/")
        if normalized.endswith(("/api", "/api/queue")):
            return normalized
        if normalized.endswith("/queue"):
            return f"{normalized.removesuffix('/queue')}/api/queue"
        return f"{normalized}/api"

    @model_validator(mode="after")
    def _auth_settings_complete(self) -> "Settings":
        if self.auth_enabled:
            for name in ("supabase_url", "supabase_publishable_key"):
                if not getattr(self, name):
                    raise ValueError(f"{name.upper()} is required when AUTH_ENABLED=true")
        return self


settings = Settings()
