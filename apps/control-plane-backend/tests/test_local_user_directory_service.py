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
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from control_plane_backend.config.models import Configuration
from control_plane_backend.users import api, service
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import (
    CreateUserRequest,
    IdentityManagedByProviderError,
)
from fastapi import FastAPI
from fred_core import KeycloakUser
from fred_core.users.store.base_user_store import AmbiguousUsernameError
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import UserRow
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine


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
        get_avatar_keys=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(service, "get_user_store", lambda: store)

    def no_admin():
        raise AssertionError("Keycloak Admin API must not be constructed")

    deps = UserServiceDependencies(
        configuration=cast(
            Configuration,
            SimpleNamespace(security=SimpleNamespace(user_directory="local")),
        ),
        create_keycloak_admin_client=no_admin,
        get_content_store=MagicMock,
    )

    assert [
        user.id
        for user in await service.list_users(
            KeycloakUser(uid=str(user_id), username="alice", roles=[]), deps
        )
    ] == [str(user_id)]
    assert [user.id for user in await service.search_users("ALI", deps)] == [
        str(user_id)
    ]
    by_id = await service.get_users_by_ids([str(user_id), "missing"], deps)
    assert by_id[str(user_id)].username == "alice"
    assert by_id["missing"].id == "missing"
    assert await service.find_user_subs_bulk(deps) == {"alice": str(user_id)}
    assert await service.find_user_sub_by_username("alice", deps) == str(user_id)
    assert await service.find_user_subs_bulk(deps, usernames=["alice"]) == {
        "alice": str(user_id)
    }
    store.find_ids_by_usernames.assert_awaited_with(["alice"])
    assert await service.user_exists_in_keycloak(str(user_id), deps) is True
    assert await service.user_exists_in_keycloak("invalid", deps) is False


@pytest.mark.asyncio
async def test_local_single_and_bulk_resolution_refuse_real_store_collisions(
    monkeypatch, tmp_path
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast(Table, UserRow.__table__).create)
    store = PostgresUserStore(engine)
    monkeypatch.setattr(service, "get_user_store", lambda: store)

    def no_admin():
        raise AssertionError("Keycloak Admin API must not be constructed")

    deps = UserServiceDependencies(
        configuration=cast(
            Configuration,
            SimpleNamespace(security=SimpleNamespace(user_directory="local")),
        ),
        create_keycloak_admin_client=no_admin,
        get_content_store=MagicMock,
    )
    try:
        for _ in range(2):
            await store.upsert_identity(uuid4(), "alice", None, None, None)
        unique_id = uuid4()
        await store.upsert_identity(unique_id, "Unique", None, None, None)

        with pytest.raises(AmbiguousUsernameError, match="alice"):
            await service.find_user_sub_by_username("alice", deps)
        with pytest.raises(AmbiguousUsernameError, match="alice"):
            await service.find_user_subs_bulk(deps)
        with pytest.raises(AmbiguousUsernameError, match="alice"):
            await service.find_user_subs_bulk(deps, usernames=["Unique", "alice"])
        assert await service.find_user_subs_bulk(deps, usernames=["Unique"]) == {
            "Unique": str(unique_id)
        }
        assert await service.find_user_sub_by_username("Unique", deps) == str(unique_id)
        assert await service.find_user_sub_by_username("unique", deps) is None
        assert await service.find_user_sub_by_username("missing", deps) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_local_user_creation_is_refused_before_admin_client() -> None:
    deps = UserServiceDependencies(
        configuration=cast(
            Configuration,
            SimpleNamespace(security=SimpleNamespace(user_directory="local")),
        ),
        create_keycloak_admin_client=lambda: (_ for _ in ()).throw(
            AssertionError("Keycloak Admin API must not be constructed")
        ),
        get_content_store=MagicMock,
    )
    request = CreateUserRequest(
        username="alice", email="alice@example.test", password=secrets.token_urlsafe()
    )

    with pytest.raises(IdentityManagedByProviderError, match="alice"):
        await service.create_user(
            KeycloakUser(uid=str(uuid4()), username="admin", roles=[]), request, deps
        )


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
