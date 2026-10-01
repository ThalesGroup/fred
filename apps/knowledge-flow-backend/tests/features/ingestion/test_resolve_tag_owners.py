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

"""Quota and task attribution use canonical SQL ownership, never ReBAC guesses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.ingestion.ingestion_controller import resolve_tag_owners


@pytest.mark.asyncio
@pytest.mark.parametrize("owner, expected", [("team-a", ({"team-a"}, set())), ("personal-alice", (set(), {"alice"})), ("unfamiliar-team-id", ({"unfamiliar-team-id"}, set()))])
async def test_attribution_uses_stored_owner_not_caller_or_other_services(monkeypatch, owner, expected):
    store = SimpleNamespace(get_tag_by_id=AsyncMock(return_value=SimpleNamespace(owner_id=owner)))
    # No ReBAC engine or team-existence API: neither is needed for attribution.
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: SimpleNamespace(get_tag_store=lambda: store))
    caller = KeycloakUser(uid="someone-else", username="caller", roles=[])
    assert await resolve_tag_owners(["folder", "folder"], caller) == expected
    store.get_tag_by_id.assert_awaited_once_with("folder")


@pytest.mark.asyncio
@pytest.mark.parametrize("folder", [None, SimpleNamespace(owner_id=None), SimpleNamespace(owner_id=""), SimpleNamespace(owner_id="personal"), SimpleNamespace(owner_id="personal-")])
async def test_missing_canonical_owner_is_never_guessed(monkeypatch, folder):
    store = SimpleNamespace(get_tag_by_id=AsyncMock(return_value=folder))
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: SimpleNamespace(get_tag_store=lambda: store))
    with pytest.raises(ValueError, match="canonical team owner"):
        await resolve_tag_owners(["folder"], KeycloakUser(uid="caller", username="caller", roles=[]))


@pytest.mark.asyncio
async def test_database_error_propagates_without_fallback(monkeypatch):
    store = SimpleNamespace(get_tag_by_id=AsyncMock(side_effect=ConnectionError("database unavailable")))
    monkeypatch.setattr(ApplicationContext, "get_instance", lambda: SimpleNamespace(get_tag_store=lambda: store))
    with pytest.raises(ConnectionError, match="database unavailable"):
        await resolve_tag_owners(["folder"], KeycloakUser(uid="caller", username="caller", roles=[]))
