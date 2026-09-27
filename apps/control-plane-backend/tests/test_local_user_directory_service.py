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

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest

from control_plane_backend.users import api, service
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import (
    CreateUserRequest,
    IdentityManagedByProviderError,
)


@pytest.mark.asyncio
async def test_local_user_reads_never_construct_admin(monkeypatch):
    user_id = uuid4()
    raw = {
        "id": str(user_id),
        "username": "alice",
        "email": "alice@example.test",
        "firstName": "Alice",
        "lastName": "Martin",
    }
    store = SimpleNamespace(
        list_identities=AsyncMock(return_value=[raw]),
        search_identities=AsyncMock(return_value=[raw]),
        get_identities=AsyncMock(return_value=[raw]),
        find_ids_by_usernames=AsyncMock(return_value={"alice": str(user_id)}),
        identity_exists=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(service, "get_user_store", lambda: store)

    def no_admin():
        raise AssertionError("Keycloak Admin API must not be constructed")

    deps = UserServiceDependencies(
        configuration=SimpleNamespace(security=SimpleNamespace(user_directory="local")),
        create_keycloak_admin_client=no_admin,
    )

    assert [user.id for user in await service.list_users(None, deps)] == [str(user_id)]
    assert [user.id for user in await service.search_users("ALI", deps)] == [
        str(user_id)
    ]
    by_id = await service.get_users_by_ids([str(user_id), "missing"], deps)
    assert by_id[str(user_id)].username == "alice"
    assert by_id["missing"].id == "missing"
    assert await service.find_user_subs_bulk(deps) == {"alice": str(user_id)}
    assert await service.find_user_sub_by_username("alice", deps) == str(user_id)
    assert await service.user_exists_in_keycloak(str(user_id), deps) is True
    assert await service.user_exists_in_keycloak("invalid", deps) is False


@pytest.mark.asyncio
async def test_local_user_creation_is_refused_before_admin_client() -> None:
    deps = UserServiceDependencies(
        configuration=SimpleNamespace(security=SimpleNamespace(user_directory="local")),
        create_keycloak_admin_client=lambda: (_ for _ in ()).throw(
            AssertionError("Keycloak Admin API must not be constructed")
        ),
    )
    request = CreateUserRequest(
        username="alice", email="alice@example.test", password=secrets.token_urlsafe()
    )

    with pytest.raises(IdentityManagedByProviderError, match="alice"):
        await service.create_user(None, request, deps)


@pytest.mark.asyncio
async def test_managed_identity_error_maps_to_http_409() -> None:
    app = FastAPI()
    api.register_exception_handlers(app)

    @app.get("/managed-identity")
    async def raise_managed_identity():
        raise IdentityManagedByProviderError("alice")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/managed-identity")

    assert response.status_code == 409
    assert response.json()["reason"] == "managed_by_identity_provider"
