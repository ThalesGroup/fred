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

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.capability_settings_models import (
    TeamCapabilitySettingsRow,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamCapabilitySettings:
    """One team's stored enablement settings for one capability (CAPAB-01)."""

    team_id: TeamId
    capability_id: str
    settings: dict[str, Any]
    updated_by: str | None
    updated_at: datetime | None


def _row_to_record(row: TeamCapabilitySettingsRow) -> TeamCapabilitySettings:
    return TeamCapabilitySettings(
        team_id=TeamId(row.team_id),
        capability_id=row.capability_id,
        settings=json.loads(row.settings_json or "{}"),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class TeamCapabilitySettingsStore:
    """The configuration half of per-team capability enablement (RFC §8.2).

    Pure CRUD over ``team_capability_settings``. The enablement service owns the
    write ordering against the FGA tuples — this store never touches OpenFGA.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert(
        self,
        *,
        team_id: TeamId,
        capability_id: str,
        settings: dict[str, Any],
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> TeamCapabilitySettings:
        """Insert or replace one team's settings row (portable upsert).

        Select-then-write rather than a dialect-specific ``ON CONFLICT`` so the
        same code path serves both the local SQLite dev DB and Postgres.
        """

        payload = json.dumps(settings, sort_keys=True)
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(TeamCapabilitySettingsRow).where(
                        TeamCapabilitySettingsRow.team_id == str(team_id),
                        TeamCapabilitySettingsRow.capability_id == capability_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    TeamCapabilitySettingsRow(
                        team_id=str(team_id),
                        capability_id=capability_id,
                        settings_json=payload,
                        updated_by=updated_by,
                    )
                )
            else:
                existing.settings_json = payload
                existing.updated_by = updated_by
        return TeamCapabilitySettings(
            team_id=team_id,
            capability_id=capability_id,
            settings=settings,
            updated_by=updated_by,
            updated_at=None,
        )

    async def get(
        self,
        *,
        team_id: TeamId,
        capability_id: str,
        session: AsyncSession | None = None,
    ) -> TeamCapabilitySettings | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamCapabilitySettingsRow).where(
                        TeamCapabilitySettingsRow.team_id == str(team_id),
                        TeamCapabilitySettingsRow.capability_id == capability_id,
                    )
                )
            ).scalar_one_or_none()
        return _row_to_record(row) if row is not None else None

    async def list_for_team(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> dict[str, dict[str, Any]]:
        """All of one team's settings, keyed by capability id (session prep)."""

        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(TeamCapabilitySettingsRow).where(
                            TeamCapabilitySettingsRow.team_id == str(team_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            row.capability_id: json.loads(row.settings_json or "{}") for row in rows
        }

    async def delete(
        self,
        *,
        team_id: TeamId,
        capability_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(TeamCapabilitySettingsRow).where(
                    TeamCapabilitySettingsRow.team_id == str(team_id),
                    TeamCapabilitySettingsRow.capability_id == capability_id,
                )
            )
