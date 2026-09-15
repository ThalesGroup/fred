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

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.platform_default_team_models import (
    PlatformDefaultTeamRow,
)


class PlatformDefaultTeamStore:
    """CRUD over `platform_default_teams`, one row per default team.

    Never checks authorization or whether the teams exist: that is
    `teams/service.py`'s job, same split as `PlatformPromptStore`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def list_team_ids(self) -> list[str]:
        async with use_session(self._sessions) as s:
            result = await s.execute(
                select(PlatformDefaultTeamRow.team_id).order_by(
                    PlatformDefaultTeamRow.team_id
                )
            )
            return list(result.scalars().all())

    async def replace(self, team_ids: list[str], *, updated_by: str | None) -> None:
        """Make `team_ids` the whole set of default teams; `[]` clears it."""
        async with use_session(self._sessions) as s:
            await s.execute(delete(PlatformDefaultTeamRow))
            s.add_all(
                PlatformDefaultTeamRow(team_id=team_id, updated_by=updated_by)
                for team_id in team_ids
            )
