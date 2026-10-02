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

"""Store-level tests for per-user prompt favorites, offline against SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.prompts.store import PromptRecord, PromptStore
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[PromptStore]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fav.sqlite3'}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    try:
        yield PromptStore(engine)
    finally:
        await engine.dispose()


async def _prompt(store: PromptStore, team: str, name: str) -> str:
    record = await store.create(
        PromptRecord(
            prompt_id=f"{team}:{name}",
            team_id=TeamId(team),
            name=name,
            description=None,
            text="hello",
            created_by="author",
        )
    )
    return record.prompt_id


@pytest.mark.asyncio
async def test_favorites_are_per_user_and_idempotent(store: PromptStore) -> None:
    a = await _prompt(store, "team-1", "a")
    b = await _prompt(store, "team-1", "b")

    await store.set_favorite("alice", a, True)
    await store.set_favorite("alice", a, True)

    assert await store.favorite_ids("alice", [a, b]) == {a}
    assert await store.favorite_ids("bob", [a, b]) == set()

    await store.set_favorite("alice", a, False)
    await store.set_favorite("alice", a, False)
    assert await store.favorite_ids("alice", [a, b]) == set()


@pytest.mark.asyncio
async def test_deleting_a_prompt_drops_its_favorites(store: PromptStore) -> None:
    a = await _prompt(store, "team-1", "a")
    await store.set_favorite("alice", a, True)

    deleted = await store.delete(a, TeamId("team-1"))
    assert deleted
    await _prompt(store, "team-1", "a")  # same id again, a new prompt

    assert await store.favorite_ids("alice", [a]) == set()


@pytest.mark.asyncio
async def test_leaving_a_team_drops_only_that_teams_favorites(
    store: PromptStore,
) -> None:
    left = await _prompt(store, "team-1", "a")
    other = await _prompt(store, "team-2", "b")
    personal = await _prompt(store, "personal-alice", "c")
    for prompt_id in (left, other, personal):
        await store.set_favorite("alice", prompt_id, True)
    await store.set_favorite("bob", left, True)

    await store.delete_favorites_for_team("alice", TeamId("team-1"))

    assert await store.favorite_ids("alice", [left, other, personal]) == {
        other,
        personal,
    }
    assert await store.favorite_ids("bob", [left]) == {left}


@pytest.mark.asyncio
async def test_deleting_an_account_drops_all_its_favorites(store: PromptStore) -> None:
    a = await _prompt(store, "team-1", "a")
    b = await _prompt(store, "team-2", "b")
    await store.set_favorite("alice", a, True)
    await store.set_favorite("alice", b, True)
    await store.set_favorite("bob", a, True)

    await store.delete_favorites_for_user("alice")

    assert await store.favorite_ids("alice", [a, b]) == set()
    assert await store.favorite_ids("bob", [a]) == {a}
