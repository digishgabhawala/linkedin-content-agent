from datetime import datetime, timedelta

import pytest

from app.db.models import ImageDeletion, Post
from app.services import archive_service


ARTIFACT_ID = "11111111-1111-4111-8111-111111111111"


def _artifact_url(base: str) -> str:
    return f"{base}/storage/v1/object/public/artifacts/{ARTIFACT_ID}.png"


def test_archive_clears_image_and_queues_deletion(db_session, monkeypatch):
    supabase_url = "https://project.supabase.co"
    monkeypatch.setattr(archive_service.image_cleanup.settings, "supabase_url", supabase_url)
    post = Post(
        owner_id="user-a", brief="b", status="ready",
        final_image_path=_artifact_url(supabase_url), image_task_id="task-1",
        image_job_error="old error",
    )
    db_session.add(post)
    db_session.commit()
    now = datetime(2026, 11, 1, 3, 0)

    rows = archive_service.archive_post(db_session, post, now=now)

    assert post.archived_at == now
    assert post.final_image_path is None
    assert post.image_task_id is None
    assert post.image_job_error is None
    assert rows == db_session.query(ImageDeletion).all()
    assert len(rows) == 1
    assert rows[0].ref == ARTIFACT_ID
    assert rows[0].reason == "archived"
    assert rows[0].post_id == post.id


def test_archive_legacy_path_clears_without_row(db_session):
    post = Post(owner_id="user-a", brief="b", status="ready",
                final_image_path="output/legacy.png")
    db_session.add(post)
    db_session.commit()

    rows = archive_service.archive_post(db_session, post)

    assert post.final_image_path is None
    assert rows == []
    assert db_session.query(ImageDeletion).count() == 0


@pytest.mark.parametrize("fields", [
    {"active_step": '{"name":"draft","task_id":"t1"}'},
    {"status": "image_queued"},
])
def test_archive_refuses_busy_post(db_session, fields):
    values = {"owner_id": "user-a", "brief": "b", "status": "drafting"}
    values.update(fields)
    post = Post(**values)
    db_session.add(post)
    db_session.commit()

    with pytest.raises(archive_service.PostBusy):
        archive_service.archive_post(db_session, post)

    assert post.archived_at is None


def test_archive_is_idempotent(db_session):
    archived_at = datetime(2026, 10, 1)
    post = Post(owner_id="user-a", brief="b", status="ready", archived_at=archived_at)
    db_session.add(post)
    db_session.commit()

    assert archive_service.archive_post(db_session, post) == []
    assert post.archived_at == archived_at


def test_unarchive_ready_post_becomes_locked(db_session):
    post = Post(owner_id="user-a", brief="b", status="ready",
                archived_at=datetime(2026, 10, 1), final_image_path=None)
    db_session.add(post)
    db_session.commit()

    result = archive_service.unarchive_post(db_session, post)

    assert result is post
    assert post.archived_at is None
    assert post.status == "locked"
    assert post.final_image_path is None


@pytest.mark.parametrize("status", ["clarifying", "needs_input", "drafting", "locked"])
def test_unarchive_text_stage_keeps_status(db_session, status):
    post = Post(owner_id="user-a", brief="b", status=status,
                archived_at=datetime(2026, 10, 1))
    db_session.add(post)
    db_session.commit()

    archive_service.unarchive_post(db_session, post)

    assert post.archived_at is None
    assert post.status == status


def test_auto_archive_date_none_when_disabled():
    post = Post(owner_id="user-a", brief="b", updated_at=datetime(2026, 10, 1))

    assert archive_service.auto_archive_date(post, days=0) is None


def test_auto_archive_date_uses_updated_at_and_skips_archived():
    updated_at = datetime(2026, 10, 1, 12, 0)
    post = Post(owner_id="user-a", brief="b", updated_at=updated_at)

    assert archive_service.auto_archive_date(post, days=30) == updated_at + timedelta(days=30)
    post.archived_at = datetime(2026, 10, 2)
    assert archive_service.auto_archive_date(post, days=30) is None
