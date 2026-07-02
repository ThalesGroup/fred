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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.team_policy_override_models import (
    TeamPolicyOverrideRow,
)


@dataclass
class TeamPolicyOverrideRecord:
    """In-memory projection of one persisted ``team_policy_override`` row."""

    team_id: str
    team_delete_grace: str | None
    max_idle: str | None
    updated_by: str
    updated_at: datetime | None = None


def _row_to_record(row: TeamPolicyOverrideRow) -> TeamPolicyOverrideRecord:
    return TeamPolicyOverrideRecord(
        team_id=row.team_id,
        team_delete_grace=row.team_delete_grace,
        max_idle=row.max_idle,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class TeamPolicyOverrideStore:
    """Pure persistence for per-team retention policy overrides.

    Why this store exists:
    - the per-team retention override (FRED-2.0.2-RGPD-READY-RFC §3.B) is a DB
      row the policy resolver layers over the static YAML catalog; this store is
      the single read/write surface for that row.

    Design rule:
    - one row per team (PK = ``team_id``), so ``upsert`` replaces the single row
      via ``s.merge``; no clamp/resolution logic lives here (that is the B3
      resolver) — this class is persistence only.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(
        self, team_id: str, session: AsyncSession | None = None
    ) -> TeamPolicyOverrideRecord | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamPolicyOverrideRow, team_id)
            if row is None:
                return None
        return _row_to_record(row)

    async def upsert(
        self,
        team_id: str,
        *,
        team_delete_grace: str | None,
        max_idle: str | None,
        updated_by: str,
        session: AsyncSession | None = None,
    ) -> TeamPolicyOverrideRecord:
        row = TeamPolicyOverrideRow(
            team_id=team_id,
            team_delete_grace=team_delete_grace,
            max_idle=max_idle,
            updated_by=updated_by,
            updated_at=utcnow(),
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)
        result = await self.get(team_id, session)
        assert result is not None
        return result
