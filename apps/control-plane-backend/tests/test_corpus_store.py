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

"""
`control_plane_backend.corpus.store.CorpusStore` (docs/swift/rfc/INDEXED-CORPUS-RFC.md
§2/§4/§10 step 4) — real SQLite engine, no mocks, same convention as
`test_platform_prompt.py`'s store-level test.
"""

from __future__ import annotations

import pytest
from control_plane_backend.corpus.store import CorpusStore
from control_plane_backend.models.base import Base
from control_plane_backend.models.corpus_models import CorpusRow
from fred_core.common import TeamId
from fred_sdk.contracts.corpus import Corpus, CorpusScope
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


async def _make_store() -> CorpusStore:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[CorpusRow.__table__])  # type: ignore[list-item]
    return CorpusStore(engine)


def _corpus(corpus_id: str = "corpus-1", *, team_id: str = "team-1") -> Corpus:
    return Corpus(
        corpus_id=corpus_id,
        name="Team FS corpus",
        corpus_type_id="local_fs_rag",
        scope=CorpusScope(team_id=team_id, tag_ids=["tag-a", "tag-b"]),
        connector_ref="/home/team/docs",
    )


async def test_create_then_get_round_trips_the_full_corpus() -> None:
    store = await _make_store()

    created = await store.create(_corpus())
    fetched = await store.get(created.corpus_id)

    assert fetched == created


async def test_get_returns_none_for_unknown_id() -> None:
    store = await _make_store()

    assert await store.get("missing") is None


async def test_list_by_team_only_returns_that_teams_corpora() -> None:
    store = await _make_store()
    await store.create(_corpus("corpus-1", team_id="team-a"))
    await store.create(_corpus("corpus-2", team_id="team-b"))

    result = await store.list_by_team(TeamId("team-a"))

    assert [c.corpus_id for c in result] == ["corpus-1"]


async def test_delete_removes_only_the_matching_team_scoped_row() -> None:
    store = await _make_store()
    await store.create(_corpus("corpus-1", team_id="team-a"))

    wrong_team = await store.delete("corpus-1", TeamId("team-b"))
    right_team = await store.delete("corpus-1", TeamId("team-a"))

    assert wrong_team is False
    assert right_team is True
    assert await store.get("corpus-1") is None
