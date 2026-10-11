from datetime import datetime, timedelta, timezone

from app.api.routes import _utc_iso


def test_naive_database_timestamp_is_serialized_as_utc():
    naive_utc = datetime(2026, 10, 11, 1, 8, 53, tzinfo=timezone.utc).replace(tzinfo=None)
    assert _utc_iso(naive_utc) == "2026-10-11T01:08:53Z"


def test_aware_timestamp_is_normalized_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert _utc_iso(datetime(2026, 10, 11, 6, 38, 53, tzinfo=ist)) == (
        "2026-10-11T01:08:53Z"
    )
