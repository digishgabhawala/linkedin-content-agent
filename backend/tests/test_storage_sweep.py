from datetime import datetime, timedelta

from app.config import settings
from app.db.models import Character, HeroCandidate, HeroGenerationRun
from app.services.storage_sweep import StoredObject, classify, discard_stale_candidates


NOW = datetime(2026, 11, 1, 12)


def _object(bucket, path, *, age_days=30):
    return StoredObject(
        bucket=bucket,
        path=path,
        size=1024,
        created_at=NOW - timedelta(days=age_days),
    )


def test_classify_keeps_recent_objects(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    objects = [
        _object("linkedin", "characters/u1/c1/candidates/new.png", age_days=6),
        _object("artifacts", "new.png", age_days=6),
    ]

    assert classify(
        objects, keep_urls=set(), keep_paths=set(), now=NOW,
        artifacts_before=NOW,
    ) == []


def test_classify_keeps_referenced_post_image_ignoring_query(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    obj = _object("artifacts", "render.png")
    url = (
        "https://project.supabase.co/storage/v1/object/public/artifacts/"
        "render.png?download=1"
    )

    assert classify(
        [obj], keep_urls={url}, keep_paths=set(), now=NOW,
        artifacts_before=NOW,
    ) == []


def test_classify_skips_artifacts_without_cutoff():
    obj = _object("artifacts", "orphan.png")

    assert classify(
        [obj], keep_urls=set(), keep_paths=set(), now=NOW,
        artifacts_before=None,
    ) == []


def test_classify_respects_artifacts_cutoff():
    cutoff = NOW - timedelta(days=10)
    before = _object("artifacts", "before.png", age_days=11)
    at_cutoff = _object("artifacts", "at-cutoff.png", age_days=10)
    after = _object("artifacts", "after.png", age_days=9)

    assert classify(
        [before, at_cutoff, after], keep_urls=set(), keep_paths=set(), now=NOW,
        artifacts_before=cutoff,
    ) == [before]


def test_classify_deletes_unreferenced_candidates_and_old_hero_png():
    candidate = _object("linkedin", "characters/u1/c1/candidates/old.png")
    hero = _object("linkedin", "characters/u1/c1/hero.png")

    assert classify(
        [candidate, hero], keep_urls=set(), keep_paths=set(), now=NOW,
        artifacts_before=None,
    ) == [candidate, hero]


def test_classify_keeps_linkedin_objects_outside_characters():
    obj = _object("linkedin", "uploads/unrelated.png")

    assert classify(
        [obj], keep_urls=set(), keep_paths=set(), now=NOW,
        artifacts_before=None,
    ) == []


def test_discard_stale_candidates_keeps_candidates_after_selection(db_session):
    selected_at = NOW - timedelta(days=10)
    character = Character(
        character_id="gtee_dev",
        owner_id="u1",
        hero_candidate_id="selected",
    )
    run = HeroGenerationRun(
        id="run-1",
        character_id=character.character_id,
        card_json="{}",
        profile="full",
        base_seed=1000,
        requested_candidates=3,
        status="completed",
    )
    selected = HeroCandidate(
        id="selected", seed=1000, status="ready",
        created_at=selected_at - timedelta(days=1), selected_at=selected_at,
    )
    stale = HeroCandidate(
        id="stale", seed=1001, status="ready",
        created_at=selected_at - timedelta(seconds=1),
    )
    newer = HeroCandidate(
        id="newer", seed=1002, status="ready",
        created_at=selected_at + timedelta(seconds=1),
    )
    run.candidates.extend([selected, stale, newer])
    db_session.add_all([character, run])
    db_session.commit()

    assert discard_stale_candidates(db_session) == 1
    assert selected.status == "ready"
    assert stale.status == "discarded"
    assert newer.status == "ready"
