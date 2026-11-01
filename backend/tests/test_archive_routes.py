from datetime import datetime, timedelta

import httpx
import pytest

from app.api import routes
from app.config import settings
from app.db.models import Feedback, ImageDeletion, Post, PostDraft


API = "/api/linkedin"
ARTIFACT_ID = "11111111-1111-4111-8111-111111111111"


def _post(api, **fields) -> Post:
    values = {
        "owner_id": "user-a",
        "character_id": "user-a-mascot",
        "brief": "b",
        "status": "ready",
        "post_text": "post text",
        "scene_instruction": "waving",
        "seed": 7,
        "clarify_transcript": "[]",
    }
    values.update(fields)
    with api.session_factory() as db:
        post = Post(**values)
        db.add(post)
        db.commit()
        db.refresh(post)
        db.expunge(post)
        return post


@pytest.mark.parametrize(("method", "suffix", "body"), [
    ("post", "/clarify", {"answer": "x"}),
    ("post", "/additional-info", {"info": "x"}),
    ("post", "/accept-draft", None),
    ("post", "/draft", None),
    ("post", "/regenerate", {"instruction": "x"}),
    ("post", "/feedback", {"stage": "draft", "user_note": "x"}),
    ("post", "/lock", None),
    ("patch", "/scene", {"scene_instruction": "x"}),
    ("patch", "/backdrop", {"scene_asset_name": None}),
    ("patch", "/character", {"character_id": "user-a-mascot"}),
    ("post", "/scene/use-latest-backdrop", None),
    ("post", "/generate-image", None),
    ("post", "/retry-step", None),
    ("post", "/finalize", None),
])
def test_archived_post_mutations_return_409_archived(api, users, method, suffix, body):
    users("user-a")
    post = _post(api, archived_at=datetime.utcnow())

    response = api.request(method, f"{API}/posts/{post.id}{suffix}", json=body)

    assert response.status_code == 409, suffix
    assert response.json()["reason"] == "archived"


def test_archived_post_still_readable(api, users):
    users("user-a")
    post = _post(api, archived_at=datetime.utcnow(),
                 active_step='{"name":"draft","task_id":"missing"}')
    with api.session_factory() as db:
        db.add(PostDraft(post_id=post.id, version=1, post_text="draft",
                         generated_by="draft"))
        db.add(Feedback(post_id=post.id, stage="draft", user_note="note"))
        db.commit()

    assert api.get(f"{API}/posts/{post.id}").status_code == 200
    assert api.get(f"{API}/posts/{post.id}/drafts").json()[0]["post_text"] == "draft"
    assert api.get(f"{API}/posts/{post.id}/feedback").json()[0]["user_note"] == "note"


def test_list_posts_filters_archived(api, users):
    users("user-a")
    active = _post(api, status="drafting")
    archived = _post(api, archived_at=datetime.utcnow())

    assert [post["id"] for post in api.get(f"{API}/posts").json()] == [active.id]
    assert [post["id"] for post in api.get(f"{API}/posts?archived=true").json()] == [archived.id]
    assert [post["id"] for post in api.get(f"{API}/posts?archived=false").json()] == [active.id]


def test_archive_route_succeeds_when_queue_delete_fails(api, users, monkeypatch):
    users("user-a")
    supabase_url = "https://project.supabase.co"
    monkeypatch.setattr(settings, "supabase_url", supabase_url)
    image_url = (
        f"{supabase_url}/storage/v1/object/public/artifacts/{ARTIFACT_ID}.png"
    )
    post = _post(api, final_image_path=image_url, image_task_id="task-1",
                 image_job_error="old error")
    api.queue.delete_error = httpx.ConnectError("queue unavailable")

    response = api.post(f"{API}/posts/{post.id}/archive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None
    assert response.json()["has_final_image"] is False
    with api.session_factory() as db:
        saved = db.get(Post, post.id)
        deletion = db.query(ImageDeletion).one()
        assert saved.final_image_path is None
        assert saved.image_task_id is None and saved.image_job_error is None
        assert deletion.deleted_at is None
        assert deletion.attempts == 1
        assert "queue unavailable" in deletion.last_error


def test_unarchived_post_can_generate_image_again(api, users):
    users("user-a")
    post = _post(api, archived_at=datetime.utcnow(), final_image_path=None)

    response = api.post(f"{API}/posts/{post.id}/unarchive")

    assert response.status_code == 200
    assert response.json()["status"] == "locked"
    assert response.json()["archived_at"] is None
    generated = api.post(f"{API}/posts/{post.id}/generate-image")
    assert generated.status_code == 200
    assert generated.json()["status"] == "image_queued"
    assert generated.json()["active_step"]["name"] == "image"


def test_serialize_auto_archive_on_only_inside_notice_window(monkeypatch):
    monkeypatch.setattr(settings, "auto_archive_days", 30)
    monkeypatch.setattr(settings, "auto_archive_notice_days", 7)
    now = datetime.utcnow()
    inside = Post(owner_id="user-a", brief="b", updated_at=now - timedelta(days=25))
    outside = Post(owner_id="user-a", brief="b", updated_at=now - timedelta(days=20))
    archived = Post(owner_id="user-a", brief="b", updated_at=now - timedelta(days=25),
                    archived_at=now)

    inside_view = routes._serialize_post(inside)
    outside_view = routes._serialize_post(outside)
    archived_view = routes._serialize_post(archived)

    assert inside_view["auto_archive_on"] is not None
    assert outside_view["auto_archive_on"] is None
    assert archived_view["auto_archive_on"] is None
    assert inside_view["archived_at"] is None
    assert archived_view["archived_at"] is not None


def test_daily_cleanup_503_without_secret(api, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    post = _post(api, updated_at=datetime.utcnow() - timedelta(days=31))

    response = api.get(
        f"{API}/internal/daily-cleanup",
        headers={"Authorization": "Bearer "},
    )

    assert response.status_code == 503
    with api.session_factory() as db:
        assert db.get(Post, post.id).archived_at is None


def test_daily_cleanup_401_wrong_or_missing_bearer(api, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "correct-secret")
    post = _post(api, updated_at=datetime.utcnow() - timedelta(days=31))

    assert api.get(f"{API}/internal/daily-cleanup").status_code == 401
    response = api.get(
        f"{API}/internal/daily-cleanup",
        headers={"Authorization": "Bearer wrong-secret"},
    )

    assert response.status_code == 401
    with api.session_factory() as db:
        assert db.get(Post, post.id).archived_at is None


def test_daily_cleanup_runs_and_retries_pending(api, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "cron-secret")
    monkeypatch.setattr(settings, "auto_archive_days", 30)
    post = _post(api, updated_at=datetime.utcnow() - timedelta(days=31))
    with api.session_factory() as db:
        deletion = ImageDeletion(
            owner_id="user-b", location="queue_artifact", ref=ARTIFACT_ID,
            reason="archived",
        )
        db.add(deletion)
        db.commit()
        deletion_id = deletion.id

    response = api.get(
        f"{API}/internal/daily-cleanup",
        headers={"Authorization": "Bearer cron-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "archived": 1,
        "deletions_retried": 1,
        "deletions_pruned": 0,
    }
    with api.session_factory() as db:
        assert db.get(Post, post.id).archived_at is not None
        assert db.get(ImageDeletion, deletion_id).deleted_at is not None
    assert api.queue.deleted == [
        f"{settings.task_queue_api_url}/artifacts/{ARTIFACT_ID}"
    ]
