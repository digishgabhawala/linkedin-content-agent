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
    data_dir: str = "data"

    default_character_id: str = "gtee_dev"
    clarify_max_turns: int = 3

    # System 1 integration (character-forge-v2), invoked via subprocess.Popen,
    # never imported -- standalone, shares nothing.
    character_forge_v2_path: str = str(_WORKSPACE_ROOT / "character-forge-v2")
    comfyui_env_python: str = str(_WORKSPACE_ROOT / "comfyui-env" / "bin" / "python")
    image_callback_base_url: str = "http://localhost:11000"
    image_stall_timeout_minutes: int = 40

    class Config:
        env_file = ".env"


settings = Settings()
