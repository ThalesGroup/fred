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
    )
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
                ),
                dict(
                    id=ids[1],
                    gcuVersionAccepted=None,
                    gcuAcceptedAt=None,
                    current_resources_storage_size=0,
                ),
                dict(
                    id=ids[2],
                    gcuVersionAccepted="V1",
                    gcuAcceptedAt=None,
                    current_resources_storage_size=7,
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
    cleanup_path = path.with_name("e6b8d2a41074_keep_gcu_acceptance_in_users.py")
    cleanup_spec = importlib.util.spec_from_file_location(
        "gcu_cleanup_migration", cleanup_path
    )
    assert cleanup_spec is not None and cleanup_spec.loader is not None
    cleanup = importlib.util.module_from_spec(cleanup_spec)
    cleanup_spec.loader.exec_module(cleanup)
    try:
        yield engine, migration, cleanup
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS user_gcu_acceptances"))
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
                'SELECT id, "gcuVersionAccepted", "gcuAcceptedAt", current_resources_storage_size FROM users ORDER BY current_resources_storage_size'
            )
        ).all()


def test_upgrade_and_downgrade_preserve_legacy_acceptance(migrated_database):
    engine, migration, cleanup = migrated_database
    before = _rows(engine)
    _run(engine, migration, "upgrade")
    _run(engine, cleanup, "upgrade")
    after = _rows(engine)
    assert [row[1] for row in after] == [None, "v1", "v1"]
    assert [(r[0], r[2], r[3]) for r in after] == [(r[0], r[2], r[3]) for r in before]
    assert sa.inspect(engine).get_table_names() == ["users"]
    _run(engine, cleanup, "downgrade")
    with engine.connect() as connection:
        history = connection.execute(
            sa.text("SELECT version, accepted_at FROM user_gcu_acceptances")
        ).all()
        assert len(history) == 2
        assert {r[0] for r in history} == {"v1"}
        assert sum(r[1] is None for r in history) == 1
    _run(engine, migration, "downgrade")
    assert _rows(engine) == before


def test_applied_history_migration_is_removed_without_changing_current_acceptance(
    migrated_database,
):
    engine, migration, cleanup = migrated_database
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = '2026-10' WHERE current_resources_storage_size = 42"
            )
        )
    before = _rows(engine)
    _run(engine, cleanup, "upgrade")
    assert _rows(engine) == before
    assert sa.inspect(engine).get_table_names() == ["users"]
    _run(engine, cleanup, "downgrade")
    with engine.connect() as connection:
        versions = set(
            connection.scalars(sa.text("SELECT version FROM user_gcu_acceptances"))
        )
    assert versions == {"v1", "2026-10"}
    assert _rows(engine) == before


def test_downgrade_refuses_to_lose_newer_acceptance(migrated_database):
    engine, migration, cleanup = migrated_database
    _run(engine, migration, "upgrade")
    _run(engine, cleanup, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = 'v2' WHERE current_resources_storage_size = 42"
            )
        )
    _run(engine, cleanup, "downgrade")
    before = _rows(engine)
    with pytest.raises(RuntimeError, match="would be lost"):
        _run(engine, migration, "downgrade")
    assert _rows(engine) == before
