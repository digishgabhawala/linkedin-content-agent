import httpx
import pytest

from app.api import routes
from app.auth import AuthUser
from app.config import settings
from app.services import hero_generation
from tests.test_steps import FakeQueue

API = "/api/linkedin"
CARD = {
    "character_id": "new_dev",
    "display_name": "New Developer",
    "base_description": "an Indian software developer mascot",
    "signature_attributes": [
        {"name": "green tee", "prompt_phrase": "green t-shirt", "color_hex": "#138808"}
    ],
    "personality": "practical and curious",
}


class StudioQueue(FakeQueue):
    def __init__(self):
        super().__init__()
        self.uploads = []

    async def post(self, url, json=None, timeout=None, content=None, headers=None):
        if "/storage/v1/object/" in url:
            self.uploads.append({"url": url, "content": content, "headers": headers})
            return httpx.Response(
                200, json={"Key": "candidate"}, request=httpx.Request("POST", url))
        return await super().post(url, json, timeout)

    async def get(self, url, timeout=None):
        if "/artifacts/" in url:
            artifact_id = url.rsplit("/", 1)[1]
            data = {"url": f"https://storage/{artifact_id}.png"}
            return httpx.Response(
                200, json=data, request=httpx.Request("GET", url))
        if url.startswith("https://storage/"):
            return httpx.Response(
                200, content=f"candidate:{url}".encode(),
                request=httpx.Request("GET", url))
        return await super().get(url, timeout)


def _create(api):
    response = api.post(f"{API}/characters", json=CARD)
    assert response.status_code == 201, response.text
    return response.json()


class _StorageContext:
    """hero_generation.storage_client() stand-in: Storage calls are recorded
    by the same fake, but arrive through the separate Storage client."""

    def __init__(self, fake):
        self.fake = fake

    async def __aenter__(self):
        return self.fake

    async def __aexit__(self, *exc):
        return False


def _studio_queue(api, monkeypatch):
    queue = StudioQueue()
    api.queue = queue
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-secret")
    monkeypatch.setattr(settings, "storage_bucket", "linkedin")
    monkeypatch.setattr(hero_generation, "storage_client", lambda: _StorageContext(queue))
    return queue


def test_storage_uploads_use_the_signed_in_users_session_when_login_is_on(monkeypatch):
    user = AuthUser(id="u1", email="a@b.c", access_token="user-jwt")
    monkeypatch.setattr(settings, "supabase_publishable_key", "publishable")
    monkeypatch.setattr(settings, "supabase_service_key", "service-secret")
    monkeypatch.setattr(settings, "auth_enabled", True)
    # Even with a service key configured, a hosted (login on) app never uses it.
    assert routes._storage_auth(user) == ("user-jwt", "publishable")
    assert routes._storage_auth(AuthUser(id="u1", email="a@b.c")) is None
    monkeypatch.setattr(settings, "auth_enabled", False)
    assert routes._storage_auth(user) == ("service-secret", "service-secret")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    assert routes._storage_auth(user) is None


def test_character_create_list_and_get_api(api):
    character = _create(api)

    assert character["character_id"] == "new_dev"
    assert character["character_card"]["trigger_token"] == "new_dev"
    assert character["hero_image_url"] is None and character["hero_version"] == 0
    assert api.get(f"{API}/characters").json()[0]["character_id"] == "new_dev"
    assert api.get(f"{API}/characters/new_dev").json() == character


def test_character_ids_are_validated_and_duplicates_conflict(api):
    _create(api)
    assert api.post(f"{API}/characters", json=CARD).status_code == 409
    invalid = {**CARD, "character_id": "Not a safe path"}
    assert api.post(f"{API}/characters", json=invalid).status_code == 422


def test_generation_api_submits_and_reports_each_candidate(api, monkeypatch):
    _create(api)
    queue = _studio_queue(api, monkeypatch)

    response = api.post(
        f"{API}/characters/new_dev/hero-generations",
        json={"candidate_count": 2, "base_seed": 7000, "profile": "lightning"})

    assert response.status_code == 202
    run = response.json()
    assert run["status"] == "running"
    assert [candidate["seed"] for candidate in run["candidates"]] == [7000, 7001]
    assert all(task["task_type"] == "hero_candidate_generation"
               for task in queue.submitted())
    assert queue.latest()["payload"]["character_card"]["character_id"] == "new_dev"
    listed = api.get(f"{API}/characters/new_dev/hero-generations").json()
    assert [item["id"] for item in listed] == [run["id"]]


def test_poll_promotes_candidates_and_lock_is_transactional(api, monkeypatch):
    _create(api)
    queue = _studio_queue(api, monkeypatch)
    run = api.post(
        f"{API}/characters/new_dev/hero-generations",
        json={"candidate_count": 2, "base_seed": 8000}).json()
    for index, task in enumerate(queue.tasks.values()):
        task.update(status="done", result={
            "hero_candidate_artifact_id": f"artifact-{index}",
            "candidate": {"seed": 8000 + index, "model_id": "fake-t2i"},
        })

    ready = api.get(
        f"{API}/characters/new_dev/hero-generations/{run['id']}").json()

    assert ready["status"] == "completed"
    assert [candidate["status"] for candidate in ready["candidates"]] == ["ready", "ready"]
    assert len(queue.uploads) == 2
    assert all("/storage/v1/object/linkedin/characters/auth-disabled/new_dev/candidates/"
               in upload["url"] for upload in queue.uploads)
    first, second = ready["candidates"]

    locked = api.post(
        f"{API}/characters/new_dev/hero-candidates/{first['id']}/lock").json()
    assert locked["character"]["hero_asset_id"] == first["asset_id"]
    assert locked["character"]["hero_candidate_id"] == first["id"]
    assert locked["character"]["hero_version"] == 1
    assert locked["candidate"]["is_active_hero"] is True
    assert locked["candidate"]["selected_at"] is not None

    # Re-lock is idempotent; choosing a different candidate creates v2.
    same = api.post(
        f"{API}/characters/new_dev/hero-candidates/{first['id']}/lock").json()
    assert same["character"]["hero_version"] == 1
    other = api.post(
        f"{API}/characters/new_dev/hero-candidates/{second['id']}/lock").json()
    assert other["character"]["hero_version"] == 2
    assert other["character"]["hero_asset_id"] == second["asset_id"]
    assert other["character"]["hero_candidate_id"] == second["id"]


def test_candidate_must_be_ready_and_belong_to_the_character(api, monkeypatch):
    _create(api)
    _studio_queue(api, monkeypatch)
    run = api.post(
        f"{API}/characters/new_dev/hero-generations",
        json={"candidate_count": 1, "base_seed": 9000}).json()
    candidate_id = run["candidates"][0]["id"]

    pending = api.post(
        f"{API}/characters/new_dev/hero-candidates/{candidate_id}/lock")
    assert pending.status_code == 409 and "not ready" in pending.json()["detail"]
    missing = api.post(
        f"{API}/characters/other_dev/hero-candidates/{candidate_id}/lock")
    assert missing.status_code == 404


@pytest.mark.parametrize("path", [
    f"{API}/characters/missing",
    f"{API}/characters/missing/hero-generations",
    f"{API}/characters/missing/hero-generations/run-1",
])
def test_missing_character_resources_are_404(api, path):
    assert api.get(path).status_code == 404
