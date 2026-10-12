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
from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.config.models import (
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.product import api
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.session_details import get_session
from control_plane_backend.sessions.store import SessionMetadataRecord
from fastapi import HTTPException
from fred_core import KeycloakUser
from fred_core.common import TeamId


def session_record(
    *,
    session_id: str = "session-1",
    team_id: str = "team-1",
    agent_instance_id: str | None = "agent-1",
    user_id: str = "alice",
    source_runtime_id: str | None = "runtime-1",
    agent_display_name: str | None = "Preserved assistant",
) -> SessionMetadataRecord:
    return SessionMetadataRecord(
        session_id=session_id,
        team_id=TeamId(team_id),
        agent_instance_id=agent_instance_id,
        user_id=user_id,
        title="History",
        source_runtime_id=source_runtime_id,
        agent_display_name=agent_display_name,
    )


def instance(*, enabled: bool = True, suspended: bool = False) -> AgentInstanceRecord:
    return AgentInstanceRecord(
        agent_instance_id="agent-1",
        team_id=TeamId("team-1"),
        template_id="runtime-1:assistant",
        source_runtime_id="runtime-1",
        source_agent_id="assistant",
        display_name="Assistant",
        description=None,
        enabled=enabled,
        created_by="alice",
        tuning=ManagedAgentTuning(role="assistant", description="assistant"),
        suspension_reason="capability_unavailable" if suspended else None,
    )


def dependencies(
    record: SessionMetadataRecord | None,
    agent: AgentInstanceRecord | None,
    *,
    source_enabled: bool = True,
    ingress: str | None = "/runtime",
):
    sessions = SimpleNamespace(get=AsyncMock(return_value=record))
    agents = SimpleNamespace(get_for_team=AsyncMock(return_value=agent))
    source = RuntimeCatalogSourceConfig(
        runtime_id="runtime-1",
        base_url="http://internal:8000",
        enabled=source_enabled,
        ingress_prefix=ingress,
    )
    deps = cast(
        ProductServiceDependencies,
        SimpleNamespace(
            configuration=SimpleNamespace(
                platform=SimpleNamespace(runtime_catalog_sources=[source])
            ),
            team_dependencies=SimpleNamespace(),
            get_session_metadata_store=lambda: sessions,
            get_agent_instance_store=lambda: agents,
        ),
    )
    return deps, agents


@pytest.mark.asyncio
async def test_deleted_agent_keeps_the_captured_history_route() -> None:
    deps, agents = dependencies(session_record(), None)
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None
    assert details.agent_deleted is True
    assert details.messages_url == "/runtime/agents/sessions/session-1/messages"
    assert details.title == "History"
    assert details.agent_display_name == "Preserved assistant"
    assert "source_runtime_id" not in details.model_dump()
    assert "internal" not in details.model_dump_json()
    agents.get_for_team.assert_awaited_once_with("agent-1", TeamId("team-1"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,suspended", [(True, False), (False, False), (True, True)]
)
async def test_existing_agent_status_does_not_gate_history(
    enabled: bool, suspended: bool
) -> None:
    deps, _ = dependencies(
        session_record(), instance(enabled=enabled, suspended=suspended)
    )
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.agent_deleted is False
    assert details.agent_display_name == "Assistant"
    assert details.messages_url == "/runtime/agents/sessions/session-1/messages"


@pytest.mark.asyncio
async def test_legacy_session_uses_its_surviving_instance() -> None:
    deps, _ = dependencies(session_record(source_runtime_id=None), instance())
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.messages_url is not None
    assert details.agent_deleted is False


@pytest.mark.asyncio
async def test_legacy_deleted_agent_does_not_guess_the_only_runtime() -> None:
    deps, _ = dependencies(session_record(source_runtime_id=None), None)
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.agent_deleted is True
    assert details.messages_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,ingress", [(False, "/runtime"), (True, None)])
async def test_unroutable_runtime_is_distinct_from_agent_deletion(
    enabled: bool, ingress: str | None
) -> None:
    deps, _ = dependencies(
        session_record(), instance(), source_enabled=enabled, ingress=ingress
    )
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.agent_deleted is False
    assert details.agent_display_name == "Assistant"
    assert details.messages_url is None


@pytest.mark.asyncio
async def test_history_route_uses_the_snapshot_instead_of_the_live_binding() -> None:
    deps, _ = dependencies(session_record(source_runtime_id="old-runtime"), instance())
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.messages_url is None


@pytest.mark.asyncio
async def test_history_url_encodes_the_session_path_segment() -> None:
    deps, _ = dependencies(session_record(session_id="session /?"), None)
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session /?", user_id="alice", deps=deps
    )
    assert details is not None
    assert details.messages_url == "/runtime/agents/sessions/session%20%2F%3F/messages"


@pytest.mark.asyncio
async def test_no_agent_identity_is_not_a_deleted_agent() -> None:
    deps, agents = dependencies(
        session_record(agent_instance_id=None, agent_display_name=None), None
    )
    details = await get_session(
        team_id=TeamId("team-1"), session_id="session-1", user_id="alice", deps=deps
    )
    assert details is not None and details.agent_deleted is False
    assert details.agent_display_name is None
    agents.get_for_team.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record",
    [None, session_record(user_id="bob"), session_record(team_id="other-team")],
)
async def test_session_detail_route_refuses_unknown_or_foreign_sessions(
    record: SessionMetadataRecord | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, agents = dependencies(record, None)
    team_access = AsyncMock(return_value=TeamId("team-1"))
    monkeypatch.setattr(api, "require_team_access", team_access)
    user = KeycloakUser(uid="alice", username="alice", roles=[], email=None)
    with pytest.raises(HTTPException) as exc:
        await api.get_team_session(TeamId("team-1"), "session-1", deps, user)
    assert exc.value.status_code == 404
    team_access.assert_awaited_once()
    agents.get_for_team.assert_not_awaited()
