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

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_name_migration_backfills_only_matching_live_agents_and_downgrades() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c82f6a91d043_preserve_session_agent_display_name.py"
    )
    spec = importlib.util.spec_from_file_location("session_agent_name_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE agent_instance (agent_instance_id TEXT PRIMARY KEY, team_id TEXT, display_name TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE session_metadata (session_id TEXT PRIMARY KEY, team_id TEXT, agent_instance_id TEXT, updated_at TEXT)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO agent_instance VALUES ('live', 'team-1', 'Live name')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO session_metadata VALUES ('owned', 'team-1', 'live', '2025-01-01'), ('foreign', 'team-2', 'live', '2025-01-01'), ('deleted', 'team-1', 'gone', '2025-01-01'), ('unbound', 'team-1', NULL, '2025-01-01')"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        records = connection.execute(
            sa.text(
                "SELECT session_id, agent_display_name, updated_at FROM session_metadata"
            )
        ).all()
        assert {r[0]: r[1] for r in records} == {
            "owned": "Live name",
            "foreign": None,
            "deleted": None,
            "unbound": None,
        }
        assert all(r[2] == "2025-01-01" for r in records)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "agent_display_name" not in {
            c["name"] for c in sa.inspect(connection).get_columns("session_metadata")
        }
        assert connection.scalar(sa.text("SELECT count(*) FROM session_metadata")) == 4
    engine.dispose()
