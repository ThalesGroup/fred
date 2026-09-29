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
from uuid import uuid4

import pytest
from fastapi import Request

from fred_core.security import oidc
from fred_core.security.structure import KeycloakUser
from fred_core.users.store.base_user_store import BaseUserStore


@pytest.mark.asyncio
async def test_person_snapshot_is_throttled_and_service_identity_is_ignored(
    monkeypatch,
):
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    clock = [100.0]
    monkeypatch.setattr(oidc.time, "monotonic", lambda: clock[0])
    store = SimpleNamespace(upsert_identity=AsyncMock())
    config = SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    user = KeycloakUser(uid=str(uuid4()), username="alice", roles=[])

    await oidc._snapshot_local_identity(user, cast(BaseUserStore, store), config)
    await oidc._snapshot_local_identity(user, cast(BaseUserStore, store), config)
    assert store.upsert_identity.await_count == 1

    clock[0] += 601
    await oidc._snapshot_local_identity(user, cast(BaseUserStore, store), config)
    assert store.upsert_identity.await_count == 2

    service = KeycloakUser(
        uid=str(uuid4()), username="service", roles=["service_agent"]
    )
    await oidc._snapshot_local_identity(service, cast(BaseUserStore, store), config)
    assert store.upsert_identity.await_count == 2
    for excluded in (
        KeycloakUser(
            uid=str(uuid4()),
            username="caller",
            roles=[],
            caller_roles=frozenset({"delegation_caller"}),
        ),
        KeycloakUser(
            uid=str(uuid4()), username="service-account", roles=[], service_account=True
        ),
        KeycloakUser(uid=str(uuid4()), username="", roles=[]),
    ):
        await oidc._snapshot_local_identity(
            excluded, cast(BaseUserStore, store), config
        )
    assert store.upsert_identity.await_count == 2
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()


@pytest.mark.asyncio
async def test_snapshot_failure_does_not_fail_authentication(monkeypatch, caplog):
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    store = SimpleNamespace(
        upsert_identity=AsyncMock(
            side_effect=RuntimeError("SQL parameters contain alice@example.test")
        )
    )
    config = SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    user = KeycloakUser(uid=str(uuid4()), username="alice", roles=[])

    await oidc._snapshot_local_identity(user, cast(BaseUserStore, store), config)

    assert not oidc._IDENTITY_SNAPSHOT_DEADLINES
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "[AUTH] Local identity snapshot failed"
    )
    assert record.exc_info is None
    assert record.exc_text is None
    assert "alice@example.test" not in caplog.text


@pytest.mark.asyncio
async def test_no_security_mock_is_not_snapshotted(monkeypatch):
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", False)
    store = SimpleNamespace(upsert_identity=AsyncMock())
    config = SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    user = KeycloakUser(uid=str(uuid4()), username="mock", roles=[])

    await oidc._snapshot_local_identity(user, cast(BaseUserStore, store), config)

    store.upsert_identity.assert_not_awaited()


@pytest.mark.asyncio
async def test_pre_gcu_profile_is_written_but_acceptance_is_not_granted(monkeypatch):
    from fastapi import HTTPException

    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    user = KeycloakUser(uid=str(uuid4()), username="alice", roles=[])
    monkeypatch.setattr(
        oidc, "get_current_user_without_gcu", AsyncMock(return_value=user)
    )
    store = SimpleNamespace(
        upsert_identity=AsyncMock(), find_user_by_id=AsyncMock(return_value=None)
    )
    config = SimpleNamespace(
        security=SimpleNamespace(user_directory="local"),
        app=SimpleNamespace(gcu_version="v1"),
    )
    assert (
        await oidc.get_current_user_before_gcu(
            Request({"type": "http"}), "token", cast(BaseUserStore, store), config
        )
        is user
    )
    store.upsert_identity.assert_awaited_once()
    with pytest.raises(HTTPException) as failure:
        await oidc._enforce_gcu(user, cast(BaseUserStore, store), config)
    assert failure.value.status_code == 403
    assert failure.value.detail == "user_not_accept_gcu"


@pytest.mark.asyncio
async def test_invalid_pre_gcu_request_does_not_write_identity(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        oidc, "get_current_user_without_gcu", AsyncMock(side_effect=HTTPException(401))
    )
    store = SimpleNamespace(upsert_identity=AsyncMock())
    with pytest.raises(HTTPException):
        await oidc.get_current_user_before_gcu(
            Request({"type": "http"}),
            "invalid",
            cast(BaseUserStore, store),
            SimpleNamespace(),
        )
    store.upsert_identity.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("delegated", [False, True])
async def test_pre_gcu_workloads_and_delegated_subjects_are_not_recorded(
    monkeypatch, delegated
):
    from fred_core.security.delegation import AssertedUser

    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    user = (
        AssertedUser(
            uid=str(uuid4()), client_id="agentic", run_id="run", agent_id="agent"
        )
        if delegated
        else KeycloakUser(uid=str(uuid4()), username="service", roles=["service_agent"])
    )
    monkeypatch.setattr(
        oidc, "get_current_user_without_gcu", AsyncMock(return_value=user)
    )
    store = SimpleNamespace(upsert_identity=AsyncMock())
    config = SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    assert (
        await oidc.get_current_user_before_gcu(
            Request({"type": "http"}), "token", cast(BaseUserStore, store), config
        )
        is user
    )
    store.upsert_identity.assert_not_awaited()
