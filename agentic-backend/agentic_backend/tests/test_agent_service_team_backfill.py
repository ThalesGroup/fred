# Copyright Thales 2025
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

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import AgentPermission, KeycloakUser, RebacReference, Resource

from agentic_backend.common.structures import Agent
from agentic_backend.core.agents import agent_service as agent_service_module
from agentic_backend.core.agents.agent_service import AgentService


def _build_user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="alice",
        roles=["user"],
        email="alice@example.com",
        groups=[],
    )


def _build_service(monkeypatch, *, store, rebac, manager) -> AgentService:
    monkeypatch.setattr(agent_service_module, "get_agent_store", lambda: store)
    monkeypatch.setattr(agent_service_module, "get_rebac_engine", lambda: rebac)
    return AgentService(agent_manager=manager)


@pytest.mark.asyncio
async def test_list_agents_backfills_team_id_from_rebac(monkeypatch):
    legacy_agent = Agent(id="a-1", name="Rico", class_path=None, enabled=True)
    store = SimpleNamespace(load_all=AsyncMock(return_value=[legacy_agent]))
    rebac = SimpleNamespace(
        enabled=True,
        lookup_user_resources=AsyncMock(
            return_value=[RebacReference(type=Resource.AGENT, id="a-1")]
        ),
        lookup_subjects=AsyncMock(
            return_value=[RebacReference(type=Resource.TEAM, id="team-bidgpt")]
        ),
    )
    manager = SimpleNamespace()

    service = _build_service(
        monkeypatch,
        store=store,
        rebac=rebac,
        manager=manager,
    )

    agents = await service.list_agents(_build_user())

    assert len(agents) == 1
    assert agents[0].id == "a-1"
    assert agents[0].team_id == "team-bidgpt"
    rebac.lookup_subjects.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_agent_by_id_backfills_team_id_from_rebac(monkeypatch):
    legacy_agent = Agent(id="a-2", name="Archie", class_path=None, enabled=True)
    store = SimpleNamespace()
    rebac = SimpleNamespace(
        enabled=True,
        check_user_permission_or_raise=AsyncMock(),
        lookup_subjects=AsyncMock(
            return_value=[RebacReference(type=Resource.TEAM, id="team-poltech")]
        ),
    )
    manager = SimpleNamespace(get_agent_settings=AsyncMock(return_value=legacy_agent))

    service = _build_service(
        monkeypatch,
        store=store,
        rebac=rebac,
        manager=manager,
    )

    resolved = await service.get_agent_by_id(_build_user(), "a-2")

    assert resolved is not None
    assert resolved.team_id == "team-poltech"
    rebac.check_user_permission_or_raise.assert_awaited_once_with(
        _build_user(), AgentPermission.READ, "a-2"
    )


@pytest.mark.asyncio
async def test_update_agent_legacy_missing_team_id_uses_rebac_owner(monkeypatch):
    persisted_legacy = Agent(id="a-3", name="Tessa", class_path=None, enabled=True)
    updated_payload = persisted_legacy.model_copy(update={"team_id": "team-bidgpt"})

    store = SimpleNamespace()
    rebac = SimpleNamespace(
        enabled=True,
        check_user_permission_or_raise=AsyncMock(),
        lookup_subjects=AsyncMock(
            return_value=[RebacReference(type=Resource.TEAM, id="team-bidgpt")]
        ),
    )
    manager = SimpleNamespace(
        get_agent_settings=AsyncMock(return_value=persisted_legacy),
        update_agent=AsyncMock(return_value=True),
    )

    service = _build_service(
        monkeypatch,
        store=store,
        rebac=rebac,
        manager=manager,
    )

    await service.update_agent(_build_user(), updated_payload)

    manager.update_agent.assert_awaited_once()
