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

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    CreateSessionRequest,
    UpdateSessionRequest,
)
from control_plane_backend.product.service import (
    create_session,
    list_sessions,
    update_session_activity,
)
from control_plane_backend.product.session_details import get_session
from control_plane_backend.sessions.store import (
    SessionMetadataRecord,
    SessionMetadataStore,
)
from fred_core import KeycloakUser
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def agent(agent_id: str = "agent-1", team: str = "team-1") -> AgentInstanceRecord:
    return AgentInstanceRecord(
        agent_instance_id=agent_id,
        team_id=TeamId(team),
        template_id="runtime:assistant",
        source_runtime_id="runtime",
        source_agent_id="assistant",
        display_name="Original name",
        description=None,
        enabled=True,
        created_by="alice",
        tuning=ManagedAgentTuning(role="assistant", description="assistant"),
    )


def deps_for(engine: AsyncEngine) -> ProductServiceDependencies:
    return cast(
        ProductServiceDependencies,
        SimpleNamespace(
            team_dependencies=SimpleNamespace(),
            get_agent_instance_store=lambda: AgentInstanceStore(engine),
            get_session_metadata_store=lambda: SessionMetadataStore(engine),
            get_kpi_writer=Mock,
            configuration=SimpleNamespace(
                platform=SimpleNamespace(runtime_catalog_sources=[])
            ),
        ),
    )


@pytest.mark.asyncio
async def test_renamed_agent_name_survives_deletion_and_session_projections(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    deps = deps_for(control_plane_sql_engine)
    agents = deps.get_agent_instance_store()
    await agents.create(agent())
    team = TeamId("team-1")
    user = cast(KeycloakUser, SimpleNamespace(uid="alice", username="alice", roles=[]))
    created = await create_session(
        user,
        team,
        CreateSessionRequest(
            session_id="session-1",
            agent_instance_id="agent-1",
            title="Conversation title",
        ),
        deps,
    )
    assert created.agent_display_name == "Original name"
    await agents.update("agent-1", team, display_name="Latest name")
    live = await get_session(
        team_id=team, session_id="session-1", user_id="alice", deps=deps
    )
    assert live is not None and live.agent_display_name == "Latest name"
    removed = await agents.delete("agent-1", team)
    assert removed
    deleted = await get_session(
        team_id=team, session_id="session-1", user_id="alice", deps=deps
    )
    assert deleted is not None and deleted.agent_deleted
    assert deleted.agent_display_name == "Latest name"
    assert deleted.updated_at is not None and created.updated_at is not None
    assert deleted.updated_at.replace(
        tzinfo=timezone.utc
    ) == created.updated_at.replace(tzinfo=timezone.utc)
    listed = await list_sessions(team, deps, user_id="alice")
    assert listed[0].agent_display_name == "Latest name"
    updated = await update_session_activity(
        team,
        "session-1",
        UpdateSessionRequest(title="Renamed conversation"),
        deps,
        user=user,
    )
    assert updated is not None and updated.agent_display_name == "Latest name"
    removed_again = await agents.delete("agent-1", team)
    assert not removed_again
    listed_after_retry = await list_sessions(team, deps, user_id="alice")
    assert listed_after_retry[0].agent_display_name == "Latest name"


@pytest.mark.asyncio
async def test_deletion_snapshots_only_its_team_and_agent_without_touching_activity(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    agents = AgentInstanceStore(control_plane_sql_engine)
    sessions = SessionMetadataStore(control_plane_sql_engine)
    await agents.create(agent())
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for sid, team, aid in [
        ("owned", "team-1", "agent-1"),
        ("foreign", "team-2", "agent-1"),
        ("other", "team-1", "agent-2"),
    ]:
        await sessions.create(
            SessionMetadataRecord(
                session_id=sid,
                team_id=TeamId(team),
                agent_instance_id=aid,
                user_id="alice",
                title=sid,
                agent_display_name="Snapshot",
                updated_at=old,
            )
        )
    removed_foreign = await agents.delete("agent-1", TeamId("team-2"))
    assert not removed_foreign
    removed_owned = await agents.delete("agent-1", TeamId("team-1"))
    assert removed_owned
    for sid, expected in [
        ("owned", "Original name"),
        ("foreign", "Snapshot"),
        ("other", "Snapshot"),
    ]:
        stored = await sessions.get(sid)
        assert stored is not None and stored.agent_display_name == expected
        assert (
            stored.updated_at is not None
            and stored.updated_at.replace(tzinfo=timezone.utc) == old
        )


@pytest.mark.asyncio
async def test_name_snapshot_and_agent_deletion_roll_back_together(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    agents = AgentInstanceStore(control_plane_sql_engine)
    sessions = SessionMetadataStore(control_plane_sql_engine)
    await agents.create(agent())
    await sessions.create(
        SessionMetadataRecord(
            session_id="session-1",
            team_id=TeamId("team-1"),
            agent_instance_id="agent-1",
            user_id="alice",
            title="Title",
            agent_display_name="Prior name",
        )
    )
    async with AsyncSession(control_plane_sql_engine) as transaction:
        async with transaction.begin():
            removed = await agents.delete(
                "agent-1", TeamId("team-1"), session=transaction
            )
            await transaction.rollback()
    assert removed
    restored_agent = await agents.get("agent-1")
    assert restored_agent is not None
    stored = await sessions.get("session-1")
    assert stored is not None and stored.agent_display_name == "Prior name"


@pytest.mark.asyncio
async def test_creation_captures_a_locked_current_agent_in_the_insert_transaction(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.dialects import postgresql

    agents = AgentInstanceStore(control_plane_sql_engine)
    await agents.create(agent())
    await agents.update("agent-1", TeamId("team-1"), display_name="Latest name")
    operations = []

    def track(connection, _cursor, statement, _parameters, context, _executemany):
        if (
            "FROM agent_instance" in statement
            or "INSERT INTO session_metadata" in statement
        ):
            operations.append(
                (
                    connection,
                    str(
                        context.compiled.statement.compile(dialect=postgresql.dialect())
                    ),
                )
            )

    event.listen(control_plane_sql_engine.sync_engine, "before_cursor_execute", track)
    try:
        stored = await SessionMetadataStore(control_plane_sql_engine).create(
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("team-1"),
                agent_instance_id="agent-1",
                user_id="alice",
                title="Title",
                agent_display_name="Stale name",
                source_runtime_id="stale-runtime",
            ),
            capture_agent_snapshot=True,
        )
    finally:
        event.remove(
            control_plane_sql_engine.sync_engine, "before_cursor_execute", track
        )
    assert (
        stored.agent_display_name == "Latest name"
        and stored.source_runtime_id == "runtime"
    )
    assert len(operations) == 2 and operations[0][0] is operations[1][0]
    assert "FOR UPDATE" in operations[0][1]
    assert "INSERT INTO session_metadata" in operations[1][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_team", ["team-1", "foreign-team"])
async def test_session_creation_refuses_deleted_or_foreign_agents_without_saving_a_row(
    control_plane_sql_engine: AsyncEngine,
    requested_team: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.product import api
    from fastapi import HTTPException

    deps = deps_for(control_plane_sql_engine)
    await deps.get_agent_instance_store().create(agent())
    if requested_team == "team-1":
        removed = await deps.get_agent_instance_store().delete(
            "agent-1", TeamId("team-1")
        )
        assert removed

    async def allowed(_user, team, _deps):
        return team

    monkeypatch.setattr(api, "require_team_access", allowed)
    with pytest.raises(HTTPException) as refused:
        await api.post_team_session(
            team_id=TeamId(requested_team),
            body=CreateSessionRequest(session_id="late", agent_instance_id="agent-1"),
            deps=deps,
            user=cast(KeycloakUser, SimpleNamespace(uid="alice")),
        )
    assert refused.value.status_code == 404
    stored = await deps.get_session_metadata_store().get("late")
    assert stored is None
