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

"""Profile picture keys on `users`: swap returns the previous key, batch read
returns only people with a picture. Runs against SQLite."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fred_core.models.base import Base
from fred_core.users.store.postgres_user_store import PostgresUserStore
from sqlalchemy.ext.asyncio import create_async_engine


async def _store(tmp_path: Path) -> PostgresUserStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return PostgresUserStore(engine)


@pytest.mark.asyncio
async def test_swap_creates_the_row_then_returns_each_previous_key(
    tmp_path: Path,
) -> None:
    store = await _store(tmp_path)
    user_id = uuid4()

    assert await store.swap_avatar_key(user_id, "users/a/avatar-1.png") is None
    row = await store.find_user_by_id(user_id)
    assert row is not None and row.avatar_object_storage_key == "users/a/avatar-1.png"

    assert (
        await store.swap_avatar_key(user_id, "users/a/avatar-2.png")
        == "users/a/avatar-1.png"
    )
    assert await store.swap_avatar_key(user_id, None) == "users/a/avatar-2.png"
    assert await store.swap_avatar_key(user_id, None) is None


@pytest.mark.asyncio
async def test_clearing_a_missing_user_creates_no_row(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    user_id = uuid4()

    assert await store.swap_avatar_key(user_id, None) is None
    assert await store.find_user_by_id(user_id) is None


@pytest.mark.asyncio
async def test_batch_read_returns_only_users_with_a_key(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    alice, bob, carol = uuid4(), uuid4(), uuid4()
    await store.swap_avatar_key(alice, "users/alice/avatar.png")
    await store.swap_avatar_key(bob, "users/bob/avatar.png")
    await store.swap_avatar_key(bob, None)

    keys = await store.get_avatar_keys(
        [str(alice), str(bob), str(carol), "service-account"]
    )

    assert keys == {str(alice): "users/alice/avatar.png"}


@pytest.mark.asyncio
async def test_batch_read_without_uuid_ids_skips_the_query(tmp_path: Path) -> None:
    store = await _store(tmp_path)

    assert await store.get_avatar_keys(["not-a-uuid"]) == {}
    assert await store.get_avatar_keys([]) == {}
