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

from typing import cast
from uuid import uuid4

import pytest
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import UserRow
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_identity_store_preserves_local_state_and_searches_each_field(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast(Table, UserRow.__table__).create)
    store = PostgresUserStore(engine)
    user_id = uuid4()
    try:
        await store.upsert_identity(
            user_id, "Alice", "alice@example.test", "Alicia", "Martin"
        )
        for query in ("ALICE", "EXAMPLE.TEST", "ALICIA", "MARTIN"):
            found = await store.search_identities(query, 10)
            assert [row["id"] for row in found] == [str(user_id)]
        assert await store.identity_exists(user_id)
        assert await store.count_identities() == 1
        assert await store.find_ids_by_usernames(["alice"]) == {"Alice": str(user_id)}
        assert await store.get_identities([user_id]) == [
            {
                "id": str(user_id),
                "username": "Alice",
                "email": "alice@example.test",
                "firstName": "Alicia",
                "lastName": "Martin",
            }
        ]
        assert await store.list_identities(0, 10) == await store.get_identities(
            [user_id]
        )
        async with engine.begin() as connection:
            await connection.execute(
                cast(Table, UserRow.__table__)
                .update()
                .where(UserRow.id == user_id)
                .values(current_resources_storage_size=123)
            )
        await store.upsert_identity(user_id, "Alice", "new@example.test", None, None)
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(UserRow.current_resources_storage_size).where(
                        UserRow.id == user_id
                    )
                )
            ).one()
        assert row.current_resources_storage_size == 123
        assert await store.count_identities() == 1
    finally:
        await engine.dispose()
