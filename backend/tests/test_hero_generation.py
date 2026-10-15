import asyncio
import json

import httpx
import pytest

from app.config import settings
from app.db.models import Character, HeroCandidate, HeroGenerationRun
from app.services.hero_generation import (
    HeroGenerationError,
    advance_generation,
    start_generation,
)

BASE = "https://project.supabase.co"
CARD = {"character_id": "gtee_dev", "trigger_token": "gtee_dev",
        "display_name": "Developer"}


def _response(status=200, *, json_body=None, content=b"", url="https://test/"):
    request = httpx.Request("GET", url)
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=request)
    return httpx.Response(status, content=content, request=request)


class HeroIO:
    def __init__(self, down=False):
        self.down = down
        self.tasks = {}
        self.submissions = []
        self.uploads = []

    async def post(self, url, json=None, content=None, headers=None, timeout=None):
        if url.endswith("/tasks"):
            if self.down:
                raise httpx.ConnectError("queue down")
            task_id = f"task-{len(self.tasks) + 1}"
            self.submissions.append(json)
            self.tasks[task_id] = {"id": task_id, "status": "queued"}
            return _response(json_body={"id": task_id, "status": "queued"}, url=url)
        self.uploads.append({"url": url, "content": content, "headers": headers})
        return _response(200, json_body={"Key": "candidate"}, url=url)

    async def get(self, url, timeout=None):
        if "/tasks/" in url:
            return _response(json_body=self.tasks[url.rsplit("/", 1)[1]], url=url)
        if "/artifacts/" in url:
            artifact_id = url.rsplit("/", 1)[1]
            return _response(json_body={"id": artifact_id,
                                        "url": f"https://queue-storage/{artifact_id}.png"},
                             url=url)
        if url.startswith("https://queue-storage/"):
            return _response(content=f"png:{url}".encode(), url=url)
        raise AssertionError(f"unexpected GET {url}")

    def finish(self, task_id, artifact_id, seed):
        self.tasks[task_id] = {
            "id": task_id,
            "status": "done",
            "result": {
                "hero_candidate_artifact_id": artifact_id,
                "candidate": {"seed": seed, "model_id": "fake-t2i",
                              "prompt": "developer mascot"},
            },
        }


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def character(db_session):
    row = Character(character_id="gtee_dev", card_json=json.dumps(CARD))
    db_session.add(row)
    db_session.commit()
    return row


def test_start_persists_run_and_submits_one_task_per_candidate(db_session, character):
    io = HeroIO()

    run = _run(start_generation(
        db_session, io, character.character_id, candidate_count=3,
        base_seed=1000, profile="lightning"))

    assert run.status == "running"
    assert run.requested_candidates == 3
    assert [candidate.seed for candidate in run.candidates] == [1000, 1001, 1002]
    assert [candidate.task_id for candidate in run.candidates] == [
        "task-1", "task-2", "task-3"]
    assert all(item["task_type"] == "hero_candidate_generation"
               for item in io.submissions)
    assert all(item["payload"]["character_card"] == CARD for item in io.submissions)
    assert db_session.query(HeroGenerationRun).count() == 1
    assert db_session.query(HeroCandidate).count() == 3


def test_queue_outage_is_persisted_once_for_the_whole_run(db_session, character):
    io = HeroIO(down=True)

    run = _run(start_generation(
        db_session, io, character.character_id, candidate_count=3, base_seed=1000))

    assert run.status == "failed"
    assert all(candidate.status == "failed" and "unreachable" in candidate.error
               for candidate in run.candidates)
    assert len(io.submissions) == 0


def test_completed_tasks_are_promoted_to_durable_storage(
        db_session, character, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", BASE)
    monkeypatch.setattr(settings, "supabase_service_key", "service-secret")
    monkeypatch.setattr(settings, "storage_bucket", "linkedin")
    io = HeroIO()
    run = _run(start_generation(
        db_session, io, character.character_id, candidate_count=2,
        base_seed=2000, profile="full"))
    for number, candidate in enumerate(run.candidates, start=1):
        io.finish(candidate.task_id, f"artifact-{number}", candidate.seed)

    run = _run(advance_generation(db_session, io, run))

    assert run.status == "completed"
    assert all(candidate.status == "ready" for candidate in run.candidates)
    assert [candidate.queue_artifact_id for candidate in run.candidates] == [
        "artifact-1", "artifact-2"]
    assert all(candidate.asset_id.startswith("sha256:") for candidate in run.candidates)
    assert all(candidate.image_url.startswith(
        f"{BASE}/storage/v1/object/public/linkedin/characters/gtee_dev/candidates/")
        for candidate in run.candidates)
    assert [json.loads(candidate.metadata_json)["seed"]
            for candidate in run.candidates] == [2000, 2001]
    assert len(io.uploads) == 2
    assert all(upload["headers"]["Authorization"] == "Bearer service-secret"
               for upload in io.uploads)
    assert all(upload["headers"]["x-upsert"] == "true" for upload in io.uploads)


def test_mixed_task_results_make_run_partial_failed(
        db_session, character, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", BASE)
    monkeypatch.setattr(settings, "supabase_service_key", "service-secret")
    io = HeroIO()
    run = _run(start_generation(
        db_session, io, character.character_id, candidate_count=2, base_seed=3000))
    io.finish(run.candidates[0].task_id, "artifact-ok", 3000)
    io.tasks[run.candidates[1].task_id] = {
        "id": run.candidates[1].task_id, "status": "failed", "error": "render failed"}

    run = _run(advance_generation(db_session, io, run))

    assert run.status == "partial_failed"
    assert [candidate.status for candidate in run.candidates] == ["ready", "failed"]
    assert run.candidates[1].error == "render failed"


def test_storage_configuration_failure_can_be_retried(
        db_session, character, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    io = HeroIO()
    run = _run(start_generation(
        db_session, io, character.character_id, candidate_count=1, base_seed=4000))
    io.finish(run.candidates[0].task_id, "artifact-retry", 4000)

    run = _run(advance_generation(db_session, io, run))
    assert run.status == "running"
    assert run.candidates[0].status == "promotion_failed"
    assert "SUPABASE_SERVICE_KEY" in run.candidates[0].error

    monkeypatch.setattr(settings, "supabase_url", BASE)
    monkeypatch.setattr(settings, "supabase_service_key", "service-secret")
    run = _run(advance_generation(db_session, io, run))
    assert run.status == "completed"
    assert run.candidates[0].status == "ready"
    assert run.candidates[0].error is None


@pytest.mark.parametrize("count, seed, profile, message", [
    (0, 1000, "full", "candidate_count"),
    (13, 1000, "full", "candidate_count"),
    (1, True, "full", "base_seed"),
    (1, 1000, "turbo", "profile"),
])
def test_invalid_generation_request_is_rejected(
        db_session, character, count, seed, profile, message):
    with pytest.raises(HeroGenerationError, match=message):
        _run(start_generation(
            db_session, HeroIO(), character.character_id, count, seed, profile))
