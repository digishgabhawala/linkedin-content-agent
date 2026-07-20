from pathlib import Path

from pydantic_settings import BaseSettings

# backend/app/config.py -> backend/app -> backend -> linkedin-content-agent -> workspace root.
# Used only to build absolute defaults below -- subprocess.Popen(cwd=...) in
# image_service.py needs an absolute path, since a relative default would
# resolve against wherever uvicorn happens to be launched from, not
# necessarily backend/.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    db_path: str = "posts.db"
    generated_dir: str = "generated"  # rendered images + placeholder; not source, safe to delete/rebuild

    default_character_id: str = "gtee_dev"
    clarify_max_turns: int = 5
    max_recalibration_passes: int = 3

    # WHO (user_profile.md) / HOW (skill.md) config -- see CONTENT_QUALITY_DESIGN.md.
    # Relative to cwd (backend/), same convention as db_path/generated_dir.
    user_profile_path: str = "content_config/user_profile.md"
    skill_path: str = "content_config/skill.md"
    example_posts_path: str = "content_config/example_posts.md"

    # character-forge-v2 integration, invoked via subprocess.Popen, never
    # imported -- standalone, shares nothing.
    character_forge_v2_path: str = str(_WORKSPACE_ROOT / "character-forge-v2")
    comfyui_env_python: str = str(_WORKSPACE_ROOT / "comfyui-env" / "bin" / "python")
    image_callback_base_url: str = "http://localhost:11000"
    image_stall_timeout_minutes: int = 40

    class Config:
        env_file = ".env"


settings = Settings()
