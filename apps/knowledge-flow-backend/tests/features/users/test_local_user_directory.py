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
from fred_core import KeycloakUser

from knowledge_flow_backend.features.users import users_service


@pytest.mark.asyncio
async def test_local_directory_reads_keep_permission_check_and_avoid_admin(monkeypatch):
    user_id = uuid4()
    raw = {"id": str(user_id), "username": "alice", "firstName": "Alice"}
    store = SimpleNamespace(
        list_identities=AsyncMock(return_value=[raw]),
        get_identities=AsyncMock(return_value=[raw]),
    )
    rebac = SimpleNamespace(check_user_permission_or_raise=AsyncMock())
    monkeypatch.setattr(users_service, "get_user_store", lambda: store)
    monkeypatch.setattr(users_service, "get_rebac_engine", lambda: rebac)
    monkeypatch.setattr(
        users_service,
        "get_configuration",
        lambda: SimpleNamespace(security=SimpleNamespace(user_directory="local")),
    )
    monkeypatch.setattr(
        users_service,
        "create_keycloak_admin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Keycloak Admin API must not be constructed")),
    )

    assert [user.id for user in await users_service.list_users(KeycloakUser(uid=str(user_id), username="alice", roles=[]))] == [str(user_id)]
    rebac.check_user_permission_or_raise.assert_awaited_once()
    by_id = await users_service.get_users_by_ids([str(user_id), "missing"])
    assert by_id[str(user_id)].username == "alice"
    assert by_id["missing"].id == "missing"
