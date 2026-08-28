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

"""#2433 — a brand-new team is private by default.

`TeamMetadataStore.create` inserts only `(id, name)` and relies on the ORM
column defaults for everything else, so the default that actually governs a
new team's visibility is `TeamMetadataRow.visibility` — exercised here
against a real (SQLite) insert, not a Pydantic-level default that a raw
insert would bypass.

Runs against SQLite, so no Postgres is needed for the default suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.common.team_id import TeamId
from fred_core.models.base import Base
from fred_core.teams.metadata_store import (
    JoiningMode,
    TeamMetadataStore,
    TeamVisibility,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path) -> AsyncEngine:
    db_path = tmp_path / "team-defaults.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_new_team_defaults_to_private_invite_only(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path)
    try:
        store = TeamMetadataStore(engine)

        created = await store.create(TeamId("team-2433"), "Swiftpost")

        assert created.visibility == TeamVisibility.PRIVATE
        assert created.joining_mode == JoiningMode.INVITE_ONLY

        # Read back through the store (not the just-returned object) so the
        # assertion covers the persisted row, not an in-memory default.
        fetched = await store.get_by_team_id(TeamId("team-2433"))
        assert fetched is not None
        assert fetched.visibility == TeamVisibility.PRIVATE
    finally:
        await engine.dispose()
