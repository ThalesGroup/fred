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
Postgres-backed store for `Corpus` instances (docs/swift/rfc/INDEXED-CORPUS-RFC.md
§2/§4/§10 step 4), mirroring `agent_instances/store.py`'s shape.

Reads and writes `fred_sdk.contracts.corpus.Corpus` directly — no separate
in-memory record class. `AgentInstanceRecord` predates that contract existing
in `fred-sdk`; `Corpus` already is the validated shape this store needs, so
adding a parallel one here would just be a second copy to keep in sync.
"""

from __future__ import annotations

import json

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.corpus import Corpus, CorpusScope
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.corpus_models import CorpusRow


def _row_to_corpus(row: CorpusRow) -> Corpus:
    return Corpus(
        corpus_id=row.corpus_id,
        name=row.name,
        corpus_type_id=row.corpus_type_id,
        scope=CorpusScope(team_id=row.team_id, tag_ids=json.loads(row.tag_ids_json)),
        connector_ref=row.connector_ref,
    )


class CorpusStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self, corpus: Corpus, session: AsyncSession | None = None
    ) -> Corpus:
        row = CorpusRow(
            corpus_id=corpus.corpus_id,
            corpus_type_id=corpus.corpus_type_id,
            team_id=corpus.scope.team_id,
            name=corpus.name,
            tag_ids_json=json.dumps(corpus.scope.tag_ids),
            connector_ref=corpus.connector_ref,
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return corpus

    async def get(
        self, corpus_id: str, session: AsyncSession | None = None
    ) -> Corpus | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(CorpusRow, corpus_id)
        return _row_to_corpus(row) if row else None

    async def list_by_team(
        self, team_id: TeamId, session: AsyncSession | None = None
    ) -> list[Corpus]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(CorpusRow).where(CorpusRow.team_id == str(team_id))
                    )
                )
                .scalars()
                .all()
            )
        return [_row_to_corpus(row) for row in rows]

    async def delete(
        self, corpus_id: str, team_id: TeamId, session: AsyncSession | None = None
    ) -> bool:
        """Delete one instance scoped to team_id. Returns True if a row was removed."""
        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(CorpusRow).where(
                    CorpusRow.corpus_id == corpus_id,
                    CorpusRow.team_id == str(team_id),
                )
            )
        return result.rowcount > 0
