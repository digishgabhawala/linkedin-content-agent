import asyncio
from datetime import datetime, timedelta

import httpx

from app.config import settings
from app.db.models import ImageDeletion, Post
from app.services import image_cleanup, llm_client


SUPABASE_URL = "https://project.supabase.co"
ARTIFACT_ID = "6dc5507a-1d60-4d85-8d13-23f80a72be1b"
OTHER_ARTIFACT_ID = "1f82375e-278a-405f-a82a-c97d81c868e0"


def _run(coro):
    return asyncio.run(coro)


def _response(status: int, url: str) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("DELETE", url))


class DeleteClient:
    def __init__(self, statuses=None, error=None):
        self.statuses = list(statuses or [])
        self.error = error
        self.calls = []

    async def delete(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return _response(self.statuses.pop(0), url)


def _deletion(**overrides) -> ImageDeletion:
    values = {
        "owner_id": "user-a",
        "location": "queue_artifact",
        "ref": ARTIFACT_ID,
        "reason": "replaced",
    }
    values.update(overrides)
    return ImageDeletion(**values)


def test_artifact_id_from_url_accepts_artifacts_bucket_url(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)

    result = image_cleanup.artifact_id_from_url(
        f"{SUPABASE_URL}/storage/v1/object/public/artifacts/{ARTIFACT_ID}.webp?v=2")

    assert result == ARTIFACT_ID


def test_artifact_id_from_url_rejects_local_path(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)

    assert image_cleanup.artifact_id_from_url(f"images/{ARTIFACT_ID}.png") is None


def test_artifact_id_from_url_rejects_other_host(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)

    assert image_cleanup.artifact_id_from_url(
        f"https://other.supabase.co/storage/v1/object/public/artifacts/{ARTIFACT_ID}.png"
    ) is None


def test_artifact_id_from_url_rejects_linkedin_bucket(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)

    assert image_cleanup.artifact_id_from_url(
        f"{SUPABASE_URL}/storage/v1/object/public/linkedin/{ARTIFACT_ID}.png"
    ) is None


def test_artifact_id_from_url_rejects_non_uuid(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)

    assert image_cleanup.artifact_id_from_url(
        f"{SUPABASE_URL}/storage/v1/object/public/artifacts/not-an-id.jpg"
    ) is None


def test_storage_path_from_url_accepts_public_linkedin_url(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(settings, "storage_bucket", "linkedin")
    path = "characters/user-a/character-a/candidates/candidate.png"

    assert image_cleanup.storage_path_from_url(
        f"{SUPABASE_URL}/storage/v1/object/public/linkedin/{path}?v=digest"
    ) == path
    assert image_cleanup.storage_path_from_url(
        f"{SUPABASE_URL}/storage/v1/object/public/artifacts/{path}"
    ) is None


def test_queue_post_image_adds_artifact_without_committing(
        db_session, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    post = Post(
        id="post-a",
        owner_id="user-a",
        brief="A post",
        final_image_path=(
            f"{SUPABASE_URL}/storage/v1/object/public/artifacts/{ARTIFACT_ID}.png"),
    )
    db_session.add(post)
    db_session.commit()

    row = image_cleanup.queue_post_image(db_session, post, "archived")

    assert row is not None
    assert row.location == "queue_artifact"
    assert row.ref == ARTIFACT_ID
    assert row.owner_id == "user-a"
    assert row.post_id == "post-a"
    assert row.reason == "archived"
    assert row in db_session.new


def test_queue_storage_object_refuses_path_outside_owner_folder(db_session):
    row = image_cleanup.queue_storage_object(
        db_session,
        owner_id="user-a",
        path="characters/character-a/candidates/x.png",
        reason="candidate_unpicked",
        character_id="character-a",
    )

    assert row is None
    assert not db_session.new


def test_queue_storage_object_adds_owned_path_without_committing(db_session):
    not_before = datetime.utcnow() + timedelta(hours=4)

    row = image_cleanup.queue_storage_object(
        db_session,
        owner_id="user-a",
        path="characters/user-a/character-a/candidates/x.png",
        reason="candidate_unpicked",
        character_id="character-a",
        not_before=not_before,
    )

    assert row is not None
    assert row.location == "linkedin_storage"
    assert row.character_id == "character-a"
    assert row.not_before == not_before
    assert row in db_session.new


def test_delete_artifact_accepts_204_and_404(monkeypatch):
    monkeypatch.setattr(settings, "task_queue_url", "https://queue.example")
    client = DeleteClient([204, 404])

    _run(llm_client.delete_artifact(client, ARTIFACT_ID))
    _run(llm_client.delete_artifact(client, OTHER_ARTIFACT_ID))

    assert [call["url"] for call in client.calls] == [
        f"https://queue.example/api/artifacts/{ARTIFACT_ID}",
        f"https://queue.example/api/artifacts/{OTHER_ARTIFACT_ID}",
    ]
    assert all(call["timeout"] == 15 for call in client.calls)


def test_attempt_marks_deleted_on_204_and_404(db_session):
    rows = [
        _deletion(ref=ARTIFACT_ID),
        _deletion(ref=OTHER_ARTIFACT_ID),
    ]
    db_session.add_all(rows)
    db_session.commit()

    _run(image_cleanup.attempt(
        db_session, rows, queue_client=DeleteClient([204, 404])))

    assert all(row.deleted_at is not None for row in rows)
    assert all(row.attempts == 0 and row.last_error is None for row in rows)


def test_attempt_records_error_and_never_raises(db_session):
    row = _deletion()
    db_session.add(row)
    db_session.commit()

    _run(image_cleanup.attempt(
        db_session,
        [row],
        queue_client=DeleteClient(error=httpx.ConnectError("queue down")),
    ))

    assert row.deleted_at is None
    assert row.attempts == 1
    assert row.last_error == "queue down"


def test_attempt_respects_not_before(db_session):
    row = _deletion(not_before=datetime.utcnow() + timedelta(hours=1))
    db_session.add(row)
    db_session.commit()
    client = DeleteClient([204])

    _run(image_cleanup.attempt(db_session, [row], queue_client=client))

    assert client.calls == []
    assert row.deleted_at is None
    assert row.attempts == 0


def test_attempt_skips_storage_rows_without_auth(db_session):
    row = _deletion(
        location="linkedin_storage",
        ref="characters/user-a/character-a/candidates/x.png",
        reason="candidate_unpicked",
    )
    db_session.add(row)
    db_session.commit()
    client = DeleteClient([200])

    _run(image_cleanup.attempt(db_session, [row], storage_client=client))

    assert client.calls == []
    assert row.deleted_at is None
    assert row.attempts == 0


def test_attempt_deletes_storage_with_user_auth_and_treats_400_as_gone(
        db_session, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(settings, "storage_bucket", "linkedin")
    path = "characters/user-a/character-a/candidates/x.png"
    row = _deletion(
        location="linkedin_storage",
        ref=path,
        reason="candidate_unpicked",
    )
    db_session.add(row)
    db_session.commit()
    client = DeleteClient([400])

    _run(image_cleanup.attempt(
        db_session,
        [row],
        storage_client=client,
        storage_auth=("user-token", "publishable-key"),
    ))

    assert row.deleted_at is not None
    assert client.calls == [{
        "url": f"{SUPABASE_URL}/storage/v1/object/linkedin/{path}",
        "headers": {
            "Authorization": "Bearer user-token",
            "apikey": "publishable-key",
        },
        "timeout": 15,
    }]


def test_pending_filters_owner_and_orders_oldest_first(db_session):
    newest = _deletion(
        id="newest", owner_id="user-a", ref=ARTIFACT_ID,
        created_at=datetime.utcnow())
    oldest = _deletion(
        id="oldest", owner_id="user-a", ref=OTHER_ARTIFACT_ID,
        created_at=datetime.utcnow() - timedelta(hours=2))
    other_owner = _deletion(
        id="other", owner_id="user-b", ref=ARTIFACT_ID,
        created_at=datetime.utcnow() - timedelta(hours=3))
    done = _deletion(
        id="done", owner_id="user-a", ref=ARTIFACT_ID,
        created_at=datetime.utcnow() - timedelta(hours=4),
        deleted_at=datetime.utcnow())
    db_session.add_all([newest, oldest, other_owner, done])
    db_session.commit()

    rows = image_cleanup.pending(
        db_session, location="queue_artifact", owner_id="user-a")

    assert [row.id for row in rows] == ["oldest", "newest"]
