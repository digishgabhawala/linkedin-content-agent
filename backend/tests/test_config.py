from app.config import Settings


def test_settings_ignore_retired_ollama_keys(tmp_path):
    # Text generation moved to the task-queue worker; existing .env files
    # still carry OLLAMA_URL/OLLAMA_MODEL and must not stop the app starting.
    env = tmp_path / ".env"
    env.write_text("OLLAMA_URL=http://localhost:11434\nOLLAMA_MODEL=qwen3:14b\n")
    settings = Settings(_env_file=env)
    assert not hasattr(settings, "ollama_url")
