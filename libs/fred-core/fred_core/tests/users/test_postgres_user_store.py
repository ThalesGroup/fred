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

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import GcuVersionsType, UserGcuAcceptanceRow, UserRow
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
async def store(tmp_path, request):
    url = f"sqlite+aiosqlite:///{tmp_path / 'users.db'}"
    if request.param == "postgresql":
        url = os.environ.get("FRED_GCU_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Set FRED_GCU_TEST_POSTGRES_URL to an isolated test database")
        assert (make_url(url).database or "").startswith("fred_gcu_test_")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: UserRow.metadata.create_all(
                sync,
                tables=[
                    UserRow.metadata.tables[UserRow.__tablename__],
                    UserGcuAcceptanceRow.metadata.tables[
                        UserGcuAcceptanceRow.__tablename__
                    ],
                ],
            )
        )
    yield PostgresUserStore(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_versions_and_first_timestamps_survive_reacceptance(store):
    uid = uuid4()
    await store.increment_current_storage_size(uid, 42)
    assert not await store.has_accepted_gcu_version(uid, "v1")
    await store.update_gcu_version(uid, GcuVersionsType.V1)
    first = await store.find_user_by_id(uid)
    await store.update_gcu_version(uid, "v2")
    assert await store.has_accepted_gcu_version(uid, "v1")
    assert await store.has_accepted_gcu_version(uid, "v2")
    assert not await store.has_accepted_gcu_version(uid, "V2")
    assert not await store.has_accepted_gcu_version(uid, "v3")
    await store.update_gcu_version(uid, "v1")
    again = await store.find_user_by_id(uid)
    assert again.gcuVersionAccepted == "v1"
    assert again.gcuAcceptedAt == first.gcuAcceptedAt
    assert again.current_resources_storage_size == 42


@pytest.mark.asyncio
async def test_concurrent_acceptance_keeps_each_version(store):
    uid = uuid4()
    await asyncio.gather(
        *(
            store.update_gcu_version(uid, version)
            for version in ["v1", "v2", "v2", "2026-10"]
        )
    )
    async with store._sessions() as session:
        versions = (
            await session.scalars(
                select(UserGcuAcceptanceRow.version).where(
                    UserGcuAcceptanceRow.user_id == uid
                )
            )
        ).all()
    assert set(versions) == {"v1", "v2", "2026-10"}
    assert len(versions) == 3
