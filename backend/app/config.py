from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    db_path: str = "posts.db"
    data_dir: str = "data"

    default_character_id: str = "gtee_dev"
    clarify_max_turns: int = 3

    # System 1 integration (character-forge-v2), invoked via subprocess.Popen,
    # never imported -- standalone, shares nothing.
    character_forge_v2_path: str = "../character-forge-v2"
    comfyui_env_python: str = "../comfyui-env/bin/python"
    image_callback_base_url: str = "http://localhost:11000"
    image_stall_timeout_minutes: int = 40

    class Config:
        env_file = ".env"


settings = Settings()
