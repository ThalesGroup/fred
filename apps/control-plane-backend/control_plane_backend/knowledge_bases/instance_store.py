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
Pure CRUD over ``knowledge_base_instances`` and ``knowledge_base_runs``.

No authorization and no orchestration: whether a team may hold this instance,
and what else must happen when one appears, is the service's business. A run
row records only that a run exists and where to find it — never its state,
which is read from the workflow engine.
"""

from __future__ import annotations

import json
import logging

from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.models import TuningValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.knowledge_base_models import (
    KnowledgeBaseInstanceRow,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseInstance:
    """One synchronized folder, as the rest of the control plane reads it."""

    def __init__(self, row: KnowledgeBaseInstanceRow) -> None:
        self.id = row.id
        self.definition_id = row.definition_id
        self.team_id = row.team_id
        self.library_id = row.library_id
        self.library_name = row.library_name
        self.schedule_json = row.schedule_json
        self.suspended = row.suspended
        self.granted_subject = row.granted_subject
        self.created_at = row.created_at
        self.updated_at = row.updated_at
        self._configuration_json = row.configuration_json

    @property
    def configuration(self) -> dict[str, TuningValue]:
        return json.loads(self._configuration_json)


class KnowledgeBaseInstanceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        *,
        instance_id: str,
        definition_id: str,
        team_id: str,
        library_id: str,
        library_name: str,
        schedule_json: str,
        suspended: bool,
        configuration: dict[str, TuningValue],
        granted_subject: str,
        created_by: str | None,
        session: AsyncSession | None = None,
    ) -> KnowledgeBaseInstance:
        async with use_session(self._sessions, session) as active:
            row = KnowledgeBaseInstanceRow(
                id=instance_id,
                definition_id=definition_id,
                team_id=team_id,
                library_id=library_id,
                library_name=library_name,
                schedule_json=schedule_json,
                suspended=suspended,
                configuration_json=json.dumps(configuration),
                granted_subject=granted_subject,
                created_by=created_by,
            )
            active.add(row)
            await active.flush()
            return KnowledgeBaseInstance(row)

    async def get(
        self, instance_id: str, *, session: AsyncSession | None = None
    ) -> KnowledgeBaseInstance | None:
        async with use_session(self._sessions, session) as active:
            row = await active.get(KnowledgeBaseInstanceRow, instance_id)
            return None if row is None else KnowledgeBaseInstance(row)

    async def list_for_team(
        self, team_id: str, *, session: AsyncSession | None = None
    ) -> list[KnowledgeBaseInstance]:
        async with use_session(self._sessions, session) as active:
            rows = await active.scalars(
                select(KnowledgeBaseInstanceRow)
                .where(KnowledgeBaseInstanceRow.team_id == team_id)
                .order_by(KnowledgeBaseInstanceRow.created_at)
            )
            return [KnowledgeBaseInstance(row) for row in rows]

    async def delete(
        self, instance_id: str, *, session: AsyncSession | None = None
    ) -> bool:
        async with use_session(self._sessions, session) as active:
            row = await active.get(KnowledgeBaseInstanceRow, instance_id)
            if row is None:
                return False
            await active.delete(row)
            return True
