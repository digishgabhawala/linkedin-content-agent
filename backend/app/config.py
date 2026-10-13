
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
    # whose email is on the allow list. Off by default so local development
    # and tests need no login; production sets AUTH_ENABLED=true.
    auth_enabled: bool = False
    supabase_url: str = ""
    supabase_publishable_key: str = ""  # browser-safe; also verifies tokens
    auth_allowed_emails: str = ""  # comma list, case-insensitive
    # How long a verified token is trusted before Supabase is asked again
    # (never past the token's own expiry). The UI polls every few seconds.
    auth_cache_minutes: float = 15

    class Config:
        env_file = ".env"
        # Retired keys (e.g. OLLAMA_URL/OLLAMA_MODEL -- text generation now
        # runs on the task-queue worker) must not stop the app starting.
        extra = "ignore"

    @property
    def allowed_emails(self) -> frozenset[str]:
        return frozenset(e.strip().casefold() for e in self.auth_allowed_emails.split(",")
                         if e.strip())

    @model_validator(mode="after")
    def _auth_settings_complete(self) -> "Settings":
        if self.auth_enabled:
            for name in ("supabase_url", "supabase_publishable_key"):
                if not getattr(self, name):
                    raise ValueError(f"{name.upper()} is required when AUTH_ENABLED=true")
            if not self.allowed_emails:
                raise ValueError("AUTH_ALLOWED_EMAILS is required when AUTH_ENABLED=true")
        return self


settings = Settings()
