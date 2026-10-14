from app.config import Settings


def test_settings_ignore_retired_ollama_keys(tmp_path):
    # Text generation moved to the task-queue worker; existing .env files
    # still carry OLLAMA_URL/OLLAMA_MODEL and must not stop the app starting.
    env = tmp_path / ".env"
    env.write_text("OLLAMA_URL=http://localhost:11434\nOLLAMA_MODEL=qwen3:14b\n")
    settings = Settings(_env_file=env)
    assert not hasattr(settings, "ollama_url")


def test_canonical_queue_page_maps_to_product_scoped_api():
    settings = Settings(
        _env_file=None,
        task_queue_url="https://ai-bharatiya-web.vercel.app/queue",
    )
    assert settings.task_queue_api_url == "https://ai-bharatiya-web.vercel.app/api/queue"


def test_local_origin_maps_to_legacy_api_mount():
    settings = Settings(_env_file=None, task_queue_url="http://127.0.0.1:8000")
    assert settings.task_queue_api_url == "http://127.0.0.1:8000/api"


def test_explicit_queue_api_base_is_unchanged():
    settings = Settings(_env_file=None, task_queue_url="https://example.test/api/queue/")
    assert settings.task_queue_api_url == "https://example.test/api/queue"
