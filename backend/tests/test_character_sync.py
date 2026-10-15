"""scripts/sync_character.py: forge workspace -> Storage + `characters` row."""
import json

import httpx
import pytest

from app.db.models import Character
from app.services.character_sync import SyncError, sync_character

PNG = b"\x89PNG\r\n\x1a\nfake"
BASE = "https://proj.supabase.co"


@pytest.fixture()
def forge(tmp_path):
    folder = tmp_path / "workspace" / "gtee_dev"
    folder.mkdir(parents=True)
    (folder / "character.json").write_text(json.dumps(
        {"character_id": "gtee_dev", "trigger_token": "gtee_dev",
         "display_name": "Dev", "personality": "asks 'but does it scale?'"}))
    (folder / "hero.png").write_bytes(PNG)
    return tmp_path


def _storage(requests, bucket_status=200, upload_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/storage/v1/bucket":
            body = "" if bucket_status == 200 else '{"message":"The resource already exists"}'
            return httpx.Response(bucket_status, text=body)
        return httpx.Response(upload_status, json={"Key": "x"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _sync(db, http, forge):
    return sync_character(db, http, BASE + "/", "service-key", "linkedin", forge, "gtee_dev")


def test_uploads_the_hero_then_writes_the_row(db_session, forge):
    requests = []
    row = _sync(db_session, _storage(requests), forge)

    bucket, upload = requests
    assert json.loads(bucket.content) == {"id": "linkedin", "name": "linkedin", "public": True}
    assert upload.url == f"{BASE}/storage/v1/object/linkedin/characters/gtee_dev/hero.png"
    assert upload.headers["x-upsert"] == "true"
    assert upload.headers["content-type"] == "image/png"
    assert upload.headers["authorization"] == "Bearer service-key"
    assert upload.content == PNG
    assert row.display_name == "Dev" and row.personality == "asks 'but does it scale?'"
    assert json.loads(row.card_json)["character_id"] == "gtee_dev"
    assert row.hero_asset_id.startswith("sha256:") and row.hero_version == 1
    url, _, version = row.hero_image_url.partition("?v=")
    assert url == f"{BASE}/storage/v1/object/public/linkedin/characters/gtee_dev/hero.png"
    assert version == row.hero_asset_id.removeprefix("sha256:")[:16]


def test_rerun_updates_the_same_row_and_accepts_an_existing_bucket(db_session, forge):
    first = _sync(db_session, _storage([]), forge)
    first_url, first_version = first.hero_image_url, first.hero_version
    second = _sync(db_session, _storage([], bucket_status=400), forge)
    assert db_session.query(Character).count() == 1
    assert second.hero_image_url == first_url
    assert second.hero_version == first_version == 1


def test_changed_hero_gets_new_asset_identity_and_version(db_session, forge):
    first = _sync(db_session, _storage([]), forge)
    first_asset_id = first.hero_asset_id
    (forge / "workspace" / "gtee_dev" / "hero.png").write_bytes(PNG + b"new")

    second = _sync(db_session, _storage([], bucket_status=400), forge)

    assert second.hero_asset_id != first_asset_id
    assert second.hero_version == 2
    assert second.hero_image_url.endswith(second.hero_asset_id.removeprefix("sha256:")[:16])


@pytest.mark.parametrize("missing", ["hero.png", "character.json"])
def test_missing_input_writes_nothing(db_session, forge, missing):
    (forge / "workspace" / "gtee_dev" / missing).unlink()
    requests = []
    with pytest.raises(SyncError, match=missing):
        _sync(db_session, _storage(requests), forge)
    assert requests == [] and db_session.query(Character).count() == 0


@pytest.mark.parametrize("statuses", [{"upload_status": 500}, {"bucket_status": 403}])
def test_storage_failure_writes_nothing(db_session, forge, statuses):
    with pytest.raises(SyncError):
        _sync(db_session, _storage([], **statuses), forge)
    assert db_session.query(Character).count() == 0
