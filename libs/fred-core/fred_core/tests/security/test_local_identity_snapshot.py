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
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from fred_core.security import oidc
from fred_core.security.structure import KeycloakUser


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

    await oidc._snapshot_local_identity(user, store, config)
    await oidc._snapshot_local_identity(user, store, config)
    assert store.upsert_identity.await_count == 1

    clock[0] += 601
    await oidc._snapshot_local_identity(user, store, config)
    assert store.upsert_identity.await_count == 2

    service = KeycloakUser(
        uid=str(uuid4()), username="service", roles=["service_agent"]
    )
    await oidc._snapshot_local_identity(service, store, config)
    assert store.upsert_identity.await_count == 2
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()


@pytest.mark.asyncio
async def test_snapshot_failure_does_not_fail_authentication(monkeypatch):
    oidc._IDENTITY_SNAPSHOT_DEADLINES.clear()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    store = SimpleNamespace(
        upsert_identity=AsyncMock(side_effect=RuntimeError("db down"))
    )
    config = SimpleNamespace(security=SimpleNamespace(user_directory="local"))
    user = KeycloakUser(uid=str(uuid4()), username="alice", roles=[])

    await oidc._snapshot_local_identity(user, store, config)

    assert not oidc._IDENTITY_SNAPSHOT_DEADLINES
