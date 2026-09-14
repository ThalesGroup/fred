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
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.platform_default_team_models import (
    PLATFORM_DEFAULT_TEAM_SINGLETON_ID,
    PlatformDefaultTeamRow,
)


class PlatformDefaultTeamStore:
    """CRUD over the `platform_default_team` singleton row.

    Never checks authorization or whether the team exists: that is
    `teams/service.py`'s job, same split as `PlatformPromptStore`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get_team_id(self) -> str | None:
        async with use_session(self._sessions) as s:
            row = await s.get(
                PlatformDefaultTeamRow, PLATFORM_DEFAULT_TEAM_SINGLETON_ID
            )
            return None if row is None else row.team_id

    async def set(self, team_id: str | None, *, updated_by: str | None) -> None:
        """Replace the default team; `None` deletes the row."""
        async with use_session(self._sessions) as s:
            row = await s.get(
                PlatformDefaultTeamRow, PLATFORM_DEFAULT_TEAM_SINGLETON_ID
            )
            if team_id is None:
                if row is not None:
                    await s.delete(row)
                return
            if row is None:
                s.add(
                    PlatformDefaultTeamRow(
                        id=PLATFORM_DEFAULT_TEAM_SINGLETON_ID,
                        team_id=team_id,
                        updated_by=updated_by,
                    )
                )
                return
            row.team_id = team_id
            row.updated_by = updated_by
            # Explicit: `onupdate` does not fire when re-saving the same team.
            row.updated_at = utcnow()
