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

from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.team_admin_charter_models import (
    TeamAdminCharterAcceptanceRow,
)


class TeamAdminCharterStore:
    """Acceptances of the team administrator charter, one row per user and version.

    Never checks authorization or the configured version: that is
    `teams/service.py`'s job, same split as `PlatformDefaultTeamStore`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get_accepted_at(self, user_id: str, version: str) -> datetime | None:
        async with use_session(self._sessions) as s:
            row = await s.get(TeamAdminCharterAcceptanceRow, (user_id, version))
            return row.accepted_at if row is not None else None

    async def accept(self, user_id: str, version: str) -> tuple[datetime, bool]:
        """Record one acceptance; return its time and whether this call inserted it."""
        existing = await self.get_accepted_at(user_id, version)
        if existing is not None:
            return existing, False
        accepted_at = utcnow()
        try:
            async with use_session(self._sessions) as s:
                s.add(
                    TeamAdminCharterAcceptanceRow(
                        user_id=user_id, version=version, accepted_at=accepted_at
                    )
                )
        except IntegrityError:
            # A concurrent request recorded the same acceptance first.
            concurrent = await self.get_accepted_at(user_id, version)
            if concurrent is None:
                raise
            return concurrent, False
        return accepted_at, True
