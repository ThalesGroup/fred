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

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.home_agents import list_home_agents
from fred_core import KeycloakUser
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.asyncio
async def test_home_agents_permissions_and_history_fallback() -> None:
    store = SimpleNamespace(
        list_home_agents=AsyncMock(side_effect=[SQLAlchemyError("history"), []])
    )
    teams = SimpleNamespace(
        rebac=SimpleNamespace(
            lookup_user_resources=AsyncMock(
                return_value=[SimpleNamespace(id="allowed")]
            )
        ),
        get_default_team_store=lambda: SimpleNamespace(
            list_team_ids=AsyncMock(return_value=["allowed", "denied"])
        ),
    )
    deps = SimpleNamespace(
        team_dependencies=teams, get_agent_instance_store=lambda: store
    )
    result = await list_home_agents(
        cast(KeycloakUser, SimpleNamespace(uid="alice")),
        cast(ProductServiceDependencies, deps),
    )
    assert result.agents == [] and result.history_unavailable
    args = store.list_home_agents.call_args_list
    assert set(args[0].args[1]) == {"allowed", "personal-alice"}
    assert set(args[0].args[2]) == {"allowed", "denied", "personal-alice"}
    assert args[1].kwargs == {"include_history": False}


@pytest.mark.asyncio
async def test_home_agents_authorization_failure_does_not_fall_back() -> None:
    store = SimpleNamespace(list_home_agents=AsyncMock())
    teams = SimpleNamespace(
        rebac=SimpleNamespace(
            lookup_user_resources=AsyncMock(
                side_effect=RuntimeError("authorization unavailable")
            )
        ),
        get_default_team_store=lambda: SimpleNamespace(
            list_team_ids=AsyncMock(return_value=[])
        ),
    )
    deps = SimpleNamespace(
        team_dependencies=teams, get_agent_instance_store=lambda: store
    )
    with pytest.raises(RuntimeError, match="authorization unavailable"):
        await list_home_agents(
            cast(KeycloakUser, SimpleNamespace(uid="alice")),
            cast(ProductServiceDependencies, deps),
        )
    store.list_home_agents.assert_not_called()


def test_activity_migration_preserves_unknown_dates_and_downgrades() -> None:
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/d7a2f591c034_add_session_last_activity.py"
    )
    spec = importlib.util.spec_from_file_location("session_activity_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE session_metadata (session_id TEXT PRIMARY KEY, user_id TEXT, agent_instance_id TEXT, updated_at TEXT)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO session_metadata VALUES ('legacy', 'alice', 'agent', '2026-01-01')"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert (
                    connection.execute(
                        sa.text("SELECT last_activity_at FROM session_metadata")
                    ).scalar()
                    is None
                )
                assert "ix_session_metadata_user_agent_activity" in {
                    i["name"]
                    for i in sa.inspect(connection).get_indexes("session_metadata")
                }
                migration.downgrade()
            assert "last_activity_at" not in {
                c["name"]
                for c in sa.inspect(connection).get_columns("session_metadata")
            }
            assert (
                connection.execute(
                    sa.text("SELECT updated_at FROM session_metadata")
                ).scalar()
                == "2026-01-01"
            )
    finally:
        engine.dispose()
