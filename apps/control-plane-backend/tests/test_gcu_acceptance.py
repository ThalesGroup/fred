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
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from control_plane_backend.teams.schemas import TeamWithPermissions
from control_plane_backend.users import api
from fastapi import FastAPI
from fred_core.common import TeamId
from fred_core.security import oidc
from fred_core.security.structure import KeycloakUser
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import UserGcuAcceptanceRow, UserRow
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_gcu_version_transition_keeps_previously_accepted_versions(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda c: UserRow.metadata.create_all(
                    c,
                    tables=[
                        UserRow.metadata.tables[UserRow.__tablename__],
                        UserGcuAcceptanceRow.metadata.tables[
                            UserGcuAcceptanceRow.__tablename__
                        ],
                    ],
                )
            )
        store = PostgresUserStore(engine)
        user = KeycloakUser(uid=str(uuid4()), username="alice", roles=[])
        configuration = SimpleNamespace(app=SimpleNamespace(gcu_version="v1"))
        deps = cast(Any, SimpleNamespace(configuration=configuration))
        team_deps = cast(Any, SimpleNamespace(configuration=configuration))
        join = AsyncMock()
        monkeypatch.setattr(api, "join_default_teams_for_new_user", join)
        monkeypatch.setattr(
            api,
            "get_team_by_id_from_service",
            AsyncMock(
                return_value=TeamWithPermissions(
                    id=TeamId(f"personal-{user.uid}"), name="Personal"
                )
            ),
        )
        monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
        app = FastAPI()

        @app.post("/gcu")
        async def accept():
            await api.validate_gcu(deps, team_deps, user, store)

        @app.get("/user")
        async def details():
            return await api.get_user_details(team_deps, user, store)

        @app.get("/protected")
        async def protected():
            await oidc._enforce_gcu(user, store, configuration)
            return {"ok": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.post("/gcu")).status_code == 200
            assert (await client.get("/user")).json()["cguValidated"] == "v1"
            configuration.app.gcu_version = "v2"
            assert (await client.get("/protected")).status_code == 403
            assert (await client.get("/user")).json()["cguValidated"] == "v1"
            assert (await client.post("/gcu")).status_code == 200
            assert (await client.get("/user")).json()["cguValidated"] == "v2"
            assert (await client.get("/protected")).status_code == 200
            configuration.app.gcu_version = "v1"
            assert (await client.get("/user")).json()["cguValidated"] == "v1"
            assert (await client.get("/protected")).status_code == 200
            join.assert_awaited_once()
            configuration.app.gcu_version = "2026-10"
            assert (await client.get("/protected")).status_code == 403
            assert (await client.post("/gcu")).status_code == 200
            assert (await client.get("/user")).json()["cguValidated"] == "2026-10"
            join.assert_awaited_once()
    finally:
        await engine.dispose()
