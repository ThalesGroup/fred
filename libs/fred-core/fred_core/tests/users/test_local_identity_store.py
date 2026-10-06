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

from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_core.users.store.base_user_store import AmbiguousUsernameError
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import GcuVersionsType, UserRow
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def identity_store(tmp_path) -> AsyncIterator[PostgresUserStore]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identities.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast(Table, UserRow.__table__).create)
    try:
        yield PostgresUserStore(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse_order", [False, True])
@pytest.mark.parametrize("names", [None, ["alice"], ["unique", "alice"]])
async def test_duplicate_usernames_are_refused_before_a_mapping_is_returned(
    identity_store: PostgresUserStore, reverse_order: bool, names: list[str] | None
) -> None:
    ids = [uuid4(), uuid4()]
    for user_id in reversed(ids) if reverse_order else ids:
        await identity_store.upsert_identity(user_id, "alice", None, None, None)
    await identity_store.upsert_identity(uuid4(), "unique", None, None, None)

    with pytest.raises(AmbiguousUsernameError) as refused:
        await identity_store.find_ids_by_usernames(names)

    assert refused.value.usernames == ("alice",)
    assert "ambiguous_username" in str(refused.value)
    assert all(str(user_id) not in str(refused.value) for user_id in ids)
    assert await identity_store.count_identities() == 3


@pytest.mark.asyncio
async def test_unrelated_collisions_and_empty_lookups_do_not_block_resolution(
    identity_store: PostgresUserStore,
) -> None:
    for _ in range(2):
        await identity_store.upsert_identity(uuid4(), "alice", None, None, None)
    unique_id = uuid4()
    await identity_store.upsert_identity(unique_id, "unique", None, None, None)

    assert await identity_store.find_ids_by_usernames(["unique"]) == {
        "unique": str(unique_id)
    }
    assert await identity_store.find_ids_by_usernames([]) == {}
    assert await identity_store.find_ids_by_usernames(["missing"]) == {}


@pytest.mark.asyncio
async def test_distinctly_cased_usernames_keep_their_exact_mapping(
    identity_store: PostgresUserStore,
) -> None:
    upper_id, lower_id = uuid4(), uuid4()
    await identity_store.upsert_identity(upper_id, "Alice", None, None, None)
    await identity_store.upsert_identity(lower_id, "alice", None, None, None)

    assert await identity_store.find_ids_by_usernames(["alice"]) == {
        "Alice": str(upper_id),
        "alice": str(lower_id),
    }


@pytest.mark.asyncio
async def test_unrequested_case_variant_collision_does_not_select_an_id(
    identity_store: PostgresUserStore,
) -> None:
    for _ in range(2):
        await identity_store.upsert_identity(uuid4(), "Alice", None, None, None)
    unique_id = uuid4()
    await identity_store.upsert_identity(unique_id, "alice", None, None, None)

    assert await identity_store.find_ids_by_usernames(["alice"]) == {
        "alice": str(unique_id)
    }
    with pytest.raises(AmbiguousUsernameError) as refused:
        await identity_store.find_ids_by_usernames(["Alice"])
    assert refused.value.usernames == ("Alice",)


@pytest.mark.asyncio
async def test_reused_username_recovers_after_the_old_snapshot_is_refreshed(
    identity_store: PostgresUserStore,
) -> None:
    old_owner, new_owner = uuid4(), uuid4()
    await identity_store.upsert_identity(old_owner, "alice", None, None, None)
    await identity_store.upsert_identity(new_owner, "bob", None, None, None)
    await identity_store.upsert_identity(new_owner, "alice", None, None, None)

    with pytest.raises(AmbiguousUsernameError):
        await identity_store.find_ids_by_usernames(["alice"])

    await identity_store.upsert_identity(old_owner, "charlie", None, None, None)

    assert await identity_store.find_ids_by_usernames(["alice"]) == {
        "alice": str(new_owner)
    }
    assert await identity_store.count_identities() == 2


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
                .values(
                    current_resources_storage_size=123,
                    gcuVersionAccepted=GcuVersionsType.V1,
                )
            )
        await store.upsert_identity(user_id, "Alice", "new@example.test", None, None)
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        UserRow.current_resources_storage_size,
                        UserRow.gcuVersionAccepted,
                    ).where(UserRow.id == user_id)
                )
            ).one()
        assert row.current_resources_storage_size == 123
        assert row.gcuVersionAccepted == GcuVersionsType.V1
        assert await store.count_identities() == 1
    finally:
        await engine.dispose()
