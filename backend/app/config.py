
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Where the app's data lives -- configuration, never hardcoded. Any
    # SQLAlchemy URL (e.g. the Supabase pooler,
    # postgresql+psycopg://...); unset means the local SQLite file at db_path.
    database_url: str | None = None
    # Postgres schema holding this app's tables (keeps them apart from other
    # apps sharing the same Supabase project). Ignored for SQLite.
    db_schema: str = "linkedin"
    db_path: str = "posts.db"  # SQLite fallback only

    default_character_id: str = "gtee_dev"
    clarify_max_turns: int = 5
    max_recalibration_passes: int = 3

    # WHO (user_profile.md) / HOW (skill.md) config -- see CONTENT_QUALITY_DESIGN.md.
    # Relative to cwd (backend/), same convention as db_path.
    user_profile_path: str = "content_config/user_profile.md"
    skill_path: str = "content_config/skill.md"
    example_posts_path: str = "content_config/example_posts.md"
    scene_examples_path: str = "content_config/scene_examples.md"

    task_queue_url: str = "http://127.0.0.1:8000"
    # This app's machine key for the task-queue (sent as X-API-Key). Its
    # sha256 is registered in task-queue's SERVICE_API_KEYS.
    task_queue_api_key: str | None = None
    # Max minutes a queued step (LLM or image) may wait for a worker before
    # the worker discards it as expired; the user can then retry the step.
    step_max_wait_minutes: float = 60
    image_stall_timeout_minutes: int = 40

    class Config:
        env_file = ".env"
        # Retired keys (e.g. OLLAMA_URL/OLLAMA_MODEL -- text generation now
        # runs on the task-queue worker) must not stop the app starting.
        extra = "ignore"


settings = Settings()
