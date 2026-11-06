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
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def migrated_database():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "agent_instance",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("team_id", sa.String(64), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("suspension_reason", sa.VARCHAR(64), nullable=True),
    )
    with engine.begin() as connection:
        metadata.create_all(connection)
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/b8e1f4a2c6d9_add_agent_instance_suspension_detail.py"
    )
    spec = importlib.util.spec_from_file_location("suspension_detail", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        yield engine, migration
    finally:
        engine.dispose()


def _run(engine, migration, operation):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, operation)()


def test_downgrade_lifts_capability_pending_suspensions(migrated_database):
    engine, migration = migrated_database
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO agent_instance (id, suspension_reason, suspension_detail) "
                "VALUES ('pending', 'capability_pending', 'Analysis failed'), "
                "('revoked', 'capability_access_revoked', NULL), "
                "('active', NULL, NULL)"
            )
        )
    _run(engine, migration, "downgrade")
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT id, suspension_reason FROM agent_instance ORDER BY id")
        ).all()
    assert rows == [
        ("active", None),
        ("pending", None),
        ("revoked", "capability_access_revoked"),
    ]
    columns = {c["name"] for c in sa.inspect(engine).get_columns("agent_instance")}
    assert "suspension_detail" not in columns
    # SQLite rebuilds the table: the unique agent-name index must survive it.
    # Expression indexes are not reflected on SQLite: read the catalog.
    with engine.connect() as connection:
        indexes = connection.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type = 'index'")
        ).scalars()
        assert "uq_agent_instance_team_name" in set(indexes)
