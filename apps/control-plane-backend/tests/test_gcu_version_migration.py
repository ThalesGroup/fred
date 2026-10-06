# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
def migrated_database(request):
    url = "sqlite://"
    if request.param == "postgresql":
        url = os.environ.get("FRED_GCU_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Set FRED_GCU_TEST_POSTGRES_URL to an isolated test database")
        assert (sa.engine.make_url(url).database or "").startswith("fred_gcu_test_")
    engine = sa.create_engine(url)
    metadata = sa.MetaData()
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "gcuVersionAccepted", sa.Enum("V1", name="gcu_version_type"), nullable=True
        ),
        sa.Column("gcuAcceptedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_resources_storage_size", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Index("ix_users_lower_username", sa.func.lower(users.c.username))
    ids = [uuid4() for _ in range(3)]
    timestamp = datetime(2026, 9, 15, 14, 10, tzinfo=timezone.utc)
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            users.insert(),
            [
                dict(
                    id=ids[0],
                    gcuVersionAccepted="V1",
                    gcuAcceptedAt=timestamp,
                    current_resources_storage_size=42,
                    username="alice",
                    email="alice@example.test",
                    first_name="Alice",
                    last_name="Tester",
                    last_seen_at=timestamp,
                ),
                dict(
                    id=ids[1],
                    gcuVersionAccepted=None,
                    gcuAcceptedAt=None,
                    current_resources_storage_size=0,
                    username=None,
                    email=None,
                    first_name=None,
                    last_name=None,
                    last_seen_at=None,
                ),
                dict(
                    id=ids[2],
                    gcuVersionAccepted="V1",
                    gcuAcceptedAt=None,
                    current_resources_storage_size=7,
                    username="missing-date",
                    email=None,
                    first_name=None,
                    last_name=None,
                    last_seen_at=None,
                ),
            ],
        )
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/a7e9c2d41063_support_configurable_gcu_versions.py"
    )
    spec = importlib.util.spec_from_file_location("gcu_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        yield engine, migration
    finally:
        with engine.begin() as connection:
            metadata.drop_all(connection)
        engine.dispose()


def _run(engine, migration, operation):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, operation)()


def _rows(engine):
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                'SELECT id, "gcuVersionAccepted", "gcuAcceptedAt", current_resources_storage_size, username, email, first_name, last_name, last_seen_at FROM users ORDER BY current_resources_storage_size'
            )
        ).all()


def _identity_index(engine):
    with engine.connect() as connection:
        if connection.dialect.name == "sqlite":
            return connection.scalar(
                sa.text(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'ix_users_lower_username'"
                )
            )
        return connection.scalar(
            sa.text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'users' AND indexname = 'ix_users_lower_username'"
            )
        )


def test_upgrade_and_downgrade_preserve_legacy_acceptance(migrated_database):
    engine, migration = migrated_database
    before = _rows(engine)
    before_index = _identity_index(engine)
    assert before_index is not None
    _run(engine, migration, "upgrade")
    after = _rows(engine)
    assert [row[1] for row in after] == [None, "v1", "v1"]
    assert [(r[0], *r[2:]) for r in after] == [(r[0], *r[2:]) for r in before]
    assert sa.inspect(engine).get_table_names() == ["users"]
    assert _identity_index(engine) == before_index
    _run(engine, migration, "downgrade")
    assert _rows(engine) == before
    assert _identity_index(engine) == before_index
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/b4e8d2a9c613_add_local_user_identity_snapshot.py"
    )
    spec = importlib.util.spec_from_file_location("identity_migration", path)
    assert spec is not None and spec.loader is not None
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    _run(engine, parent, "downgrade")
    assert _identity_index(engine) is None


def test_upgraded_column_accepts_deployment_owned_versions(migrated_database):
    engine, migration = migrated_database
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = '2026-10' WHERE current_resources_storage_size = 42"
            )
        )
    assert _rows(engine)[2][1] == "2026-10"
    assert sa.inspect(engine).get_table_names() == ["users"]


def test_downgrade_refuses_to_lose_newer_acceptance(migrated_database):
    engine, migration = migrated_database
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = 'v2' WHERE current_resources_storage_size = 42"
            )
        )
    before = _rows(engine)
    before_columns = [
        (c["name"], str(c["type"])) for c in sa.inspect(engine).get_columns("users")
    ]
    with pytest.raises(RuntimeError, match="would be lost"):
        _run(engine, migration, "downgrade")
    assert _rows(engine) == before
    assert [
        (c["name"], str(c["type"])) for c in sa.inspect(engine).get_columns("users")
    ] == before_columns
