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

"""#2149 — `increment_current_storage_size` must never leave a negative usage.

Releasing document storage on delete (knowledge-flow `metadata/service.py`)
made these stores take negative deltas on a normal path for the first time.
A counter that predates the accounting fix — or one whose matching increment
was never charged — can be released below zero, and a negative usage silently
hands out free quota, because `check_quota` compares `current + delta` against
the limit. Both stores clamp at 0 and warn instead.

Runs against SQLite, so no Postgres is needed for the default suite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fred_core.common.team_id import TeamId
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.metadata_store import TeamMetadataStore
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import UserRow
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def _seed_team(engine: AsyncEngine, team_id: str, current: int) -> None:
    sessions = make_session_factory(engine)
    async with sessions() as s:
        async with s.begin():
            s.add(
                TeamMetadataRow(
                    id=team_id,
                    name=f"name-{team_id}",
                    current_resources_storage_size=current,
                )
            )


async def _read_team(engine: AsyncEngine, team_id: str) -> int | None:
    store = TeamMetadataStore(engine)
    meta = await store.get_by_team_id(TeamId(team_id))
    assert meta is not None
    return meta.current_resources_storage_size


@pytest.mark.asyncio
async def test_team_release_subtracts_the_released_bytes(tmp_path: Path) -> None:
    """Ordinary case: deleting a 40-byte document off a 100-byte team leaves 60."""
    engine = await _make_sqlite_engine(tmp_path, "team-normal.db")
    await _seed_team(engine, "team-a", 100)

    await TeamMetadataStore(engine).increment_current_storage_size(
        TeamId("team-a"), -40
    )

    assert await _read_team(engine, "team-a") == 60


@pytest.mark.asyncio
async def test_team_release_below_zero_is_clamped(tmp_path: Path) -> None:
    """Drift guard: a release larger than the recorded usage floors at 0, never
    -200, which `check_quota` would otherwise read as 200 bytes of free quota."""
    engine = await _make_sqlite_engine(tmp_path, "team-clamp.db")
    await _seed_team(engine, "team-b", 100)

    await TeamMetadataStore(engine).increment_current_storage_size(
        TeamId("team-b"), -300
    )

    assert await _read_team(engine, "team-b") == 0


def test_a_negative_file_size_is_rejected_at_the_boundary() -> None:
    """#2149 review finding — a negative size inverts the accounting.

    Release computes `-old_size`, so a document recorded at -4096 bytes *adds*
    4096 to its owner's usage when deleted, minting free quota. Import preserves
    raw document JSON, so the model is where an out-of-band value must be
    rejected rather than persisted.
    """
    from fred_core.documents.document_structures import FileInfo

    with pytest.raises(ValidationError):
        FileInfo(file_size_bytes=-4096)

    assert FileInfo(file_size_bytes=0).file_size_bytes == 0
    assert FileInfo(file_size_bytes=None).file_size_bytes is None


@pytest.mark.asyncio
async def test_concurrent_team_releases_are_not_lost(tmp_path: Path) -> None:
    """#2149 review finding — the load-bearing concurrency guarantee.

    Deleting a library fans out one release per document with `asyncio.gather`
    (`tag_service._delete_one_tag`). The previous read-modify-write implementation
    let each coroutine read the same starting value and write back an absolute
    result, so all but one decrement was silently lost and the phantom usage
    survived the delete. Ten concurrent releases must land all ten.
    """
    engine = await _make_sqlite_engine(tmp_path, "team-concurrent.db")
    await _seed_team(engine, "team-c", 10 * 4096)
    store = TeamMetadataStore(engine)

    await asyncio.gather(
        *(
            store.increment_current_storage_size(TeamId("team-c"), -4096)
            for _ in range(10)
        )
    )

    assert await _read_team(engine, "team-c") == 0


@pytest.mark.asyncio
async def test_concurrent_user_releases_are_not_lost(tmp_path: Path) -> None:
    """Personal-space counterpart of the team concurrency guarantee above."""
    engine = await _make_sqlite_engine(tmp_path, "user-concurrent.db")
    store = PostgresUserStore(engine)
    sessions = make_session_factory(engine)
    user_id = uuid4()
    async with sessions() as s:
        async with s.begin():
            s.add(
                UserRow(
                    id=user_id,
                    gcuVersionAccepted=None,
                    gcuAcceptedAt=None,
                    current_resources_storage_size=10 * 4096,
                )
            )

    await asyncio.gather(
        *(store.increment_current_storage_size(user_id, -4096) for _ in range(10))
    )

    user = await store.find_user_by_id(user_id)
    assert user is not None and user.current_resources_storage_size == 0


@pytest.mark.asyncio
async def test_user_release_subtracts_then_clamps(tmp_path: Path) -> None:
    """Personal-space counterpart of the two team cases above."""
    engine = await _make_sqlite_engine(tmp_path, "user.db")
    store = PostgresUserStore(engine)
    sessions = make_session_factory(engine)
    user_id = uuid4()
    async with sessions() as s:
        async with s.begin():
            s.add(
                UserRow(
                    id=user_id,
                    gcuVersionAccepted=None,
                    gcuAcceptedAt=None,
                    current_resources_storage_size=100,
                )
            )

    await store.increment_current_storage_size(user_id, -40)
    user = await store.find_user_by_id(user_id)
    assert user is not None and user.current_resources_storage_size == 60

    await store.increment_current_storage_size(user_id, -300)
    user = await store.find_user_by_id(user_id)
    assert user is not None and user.current_resources_storage_size == 0


@pytest.mark.asyncio
async def test_user_release_for_an_unknown_user_records_zero_not_a_negative(
    tmp_path: Path,
) -> None:
    """The store creates a row for an unseen user. A release arriving before any
    charge (deleted user re-created, backfill not yet run) must not seed that row
    with a negative usage."""
    engine = await _make_sqlite_engine(tmp_path, "user-unknown.db")
    store = PostgresUserStore(engine)
    user_id = uuid4()

    await store.increment_current_storage_size(user_id, -500)

    user = await store.find_user_by_id(user_id)
    assert user is not None and user.current_resources_storage_size == 0
