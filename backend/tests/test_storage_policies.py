import pytest
from sqlalchemy import create_engine

from app.db import database
from app.db.storage_policies import apply_storage_policies, policy_statements


def test_policies_are_scoped_to_the_bucket_characters_folder():
    statements = policy_statements("linkedin")
    creates = [s for s in statements if s.startswith("create policy")]
    assert len(creates) == 4  # select + insert + update for upsert, plus delete
    assert all("to authenticated" in s for s in creates)
    assert all("bucket_id = 'linkedin'" in s and "= 'characters'" in s for s in creates)


def test_policy_statements_include_owner_scoped_delete():
    statements = policy_statements("linkedin")
    delete = next(s for s in statements if " for delete " in s)
    assert "for delete to authenticated using (" in delete
    assert "(storage.foldername(name))[2] = (select auth.uid()::text)" in delete


@pytest.mark.parametrize("bucket", ["", "Bad", "x'; drop table posts; --", "a" * 64])
def test_unsafe_bucket_names_are_refused(bucket):
    with pytest.raises(ValueError):
        policy_statements(bucket)


def test_sqlite_is_a_no_op():
    assert apply_storage_policies(create_engine("sqlite://"), "linkedin") is False


def test_added_columns_use_types_postgres_accepts():
    # Found live: DATETIME is valid in SQLite but not Postgres, so the
    # production migration failed while every SQLite test passed.
    portable = ("TEXT", "INTEGER", "FLOAT", "DOUBLE PRECISION", "BOOLEAN", "TIMESTAMP")
    for name in dir(database):
        if name.startswith("_NEW_") and name.endswith("_COLUMNS"):
            for column, coltype in getattr(database, name).items():
                assert coltype.split()[0] in portable or coltype.startswith(portable), \
                    f"{name}.{column}: {coltype}"


def test_writes_are_limited_to_the_users_own_folder():
    creates = [s for s in policy_statements("linkedin") if s.startswith("create policy")]
    assert all("(storage.foldername(name))[2] = (select auth.uid()::text)" in s for s in creates)
