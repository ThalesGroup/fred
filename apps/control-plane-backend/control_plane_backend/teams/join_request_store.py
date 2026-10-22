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

"""Storage of team join requests. No authorization here; every read ignores
expired rows, and every decision is a conditional write so two admins
deciding at once cannot both win."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, cast

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import CursorResult, and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.team_join_request_models import TeamJoinRequestRow

#: How long a pending request waits for a decision.
PENDING_TTL = timedelta(days=30)
#: How long a refused request stays acceptable ("Accept anyway").
REFUSED_TTL = timedelta(days=7)
#: How long a refused requester waits before asking again.
ASK_AGAIN_DELAY = timedelta(hours=24)


class JoinRequestStatus(str, Enum):
    PENDING = "pending"
    REFUSED = "refused"


@dataclass(frozen=True)
class StoredJoinRequest:
    id: str
    team_id: str
    requester_id: str
    requester_name: str
    message: str | None
    status: JoinRequestStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by: str | None

    @property
    def can_ask_again_at(self) -> datetime | None:
        if self.status != JoinRequestStatus.REFUSED or self.decided_at is None:
            return None
        return self.decided_at + ASK_AGAIN_DELAY


def request_group(request_id: str) -> str:
    """The admins' notification group of one request."""
    return f"join_request:{request_id}"


def _aware(value: datetime) -> datetime:
    # SQLite hands timestamps back naive; they were written in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _to_stored(row: TeamJoinRequestRow) -> StoredJoinRequest:
    return StoredJoinRequest(
        id=row.id,
        team_id=row.team_id,
        requester_id=row.requester_id,
        requester_name=row.requester_name,
        message=row.message,
        status=JoinRequestStatus(row.status),
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        decided_at=row.decided_at and _aware(row.decided_at),
        decided_by=row.decided_by,
    )


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount


def _live(now: datetime) -> Any:
    return TeamJoinRequestRow.expires_at > now


class TeamJoinRequestStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def _select(self, *conditions: Any) -> list[StoredJoinRequest]:
        query = (
            select(TeamJoinRequestRow)
            .where(_live(utcnow()), *conditions)
            .order_by(TeamJoinRequestRow.created_at, TeamJoinRequestRow.id)
        )
        async with use_session(self._sessions) as s:
            return [_to_stored(row) for row in (await s.execute(query)).scalars()]

    async def get_mine(
        self, team_id: str, requester_id: str
    ) -> StoredJoinRequest | None:
        rows = await self._select(
            TeamJoinRequestRow.team_id == team_id,
            TeamJoinRequestRow.requester_id == requester_id,
        )
        return rows[0] if rows else None

    async def get(self, team_id: str, request_id: str) -> StoredJoinRequest | None:
        rows = await self._select(
            TeamJoinRequestRow.team_id == team_id, TeamJoinRequestRow.id == request_id
        )
        return rows[0] if rows else None

    async def list_for_requester(self, requester_id: str) -> list[StoredJoinRequest]:
        return await self._select(TeamJoinRequestRow.requester_id == requester_id)

    async def list_for_team(self, team_id: str) -> list[StoredJoinRequest]:
        return await self._select(TeamJoinRequestRow.team_id == team_id)

    async def create(
        self,
        *,
        team_id: str,
        requester_id: str,
        requester_name: str,
        message: str | None,
    ) -> StoredJoinRequest | None:
        """A new pending request, replacing an expired one or a refusal older
        than `ASK_AGAIN_DELAY`. `None` when a live request already holds the
        slot (the caller re-reads it)."""
        now = utcnow()
        row = TeamJoinRequestRow(
            id=str(uuid.uuid4()),
            team_id=team_id,
            requester_id=requester_id,
            requester_name=requester_name,
            message=message,
            status=JoinRequestStatus.PENDING.value,
            created_at=now,
            expires_at=now + PENDING_TTL,
        )
        try:
            async with use_session(self._sessions) as s:
                await s.execute(
                    delete(TeamJoinRequestRow).where(
                        TeamJoinRequestRow.team_id == team_id,
                        TeamJoinRequestRow.requester_id == requester_id,
                        or_(
                            TeamJoinRequestRow.expires_at <= now,
                            and_(
                                TeamJoinRequestRow.status
                                == JoinRequestStatus.REFUSED.value,
                                TeamJoinRequestRow.decided_at <= now - ASK_AGAIN_DELAY,
                            ),
                        ),
                    )
                )
                s.add(row)
        except IntegrityError:
            return None
        return _to_stored(row)

    async def delete_pending_mine(
        self, team_id: str, requester_id: str
    ) -> StoredJoinRequest | None:
        """Cancel: the caller's pending request, if they still have one."""
        mine = await self.get_mine(team_id, requester_id)
        if mine is None or mine.status != JoinRequestStatus.PENDING:
            return None
        return mine if await self._delete_if_unchanged(mine) else None

    async def claim(self, team_id: str, request_id: str) -> StoredJoinRequest | None:
        """Accept: delete the request unless another decision got there first."""
        request = await self.get(team_id, request_id)
        if request is None:
            return None
        return request if await self._delete_if_unchanged(request) else None

    async def _delete_if_unchanged(self, request: StoredJoinRequest) -> bool:
        async with use_session(self._sessions) as s:
            result = await s.execute(
                delete(TeamJoinRequestRow).where(
                    TeamJoinRequestRow.id == request.id,
                    TeamJoinRequestRow.status == request.status.value,
                    _live(utcnow()),
                )
            )
            return _rowcount(result) == 1

    async def refuse(
        self, team_id: str, request_ids: Sequence[str], *, decided_by: str
    ) -> list[StoredJoinRequest]:
        """Refuse the still pending ones among `request_ids`; returns those."""
        if not request_ids:
            return []
        now = utcnow()
        pending = [
            TeamJoinRequestRow.team_id == team_id,
            TeamJoinRequestRow.id.in_(list(request_ids)),
            TeamJoinRequestRow.status == JoinRequestStatus.PENDING.value,
            _live(now),
        ]
        async with use_session(self._sessions) as s:
            ids = list(
                (
                    await s.execute(select(TeamJoinRequestRow.id).where(*pending))
                ).scalars()
            )
            if not ids:
                return []
            await s.execute(
                update(TeamJoinRequestRow)
                .where(*pending, TeamJoinRequestRow.id.in_(ids))
                .values(
                    status=JoinRequestStatus.REFUSED.value,
                    decided_at=now,
                    decided_by=decided_by,
                    expires_at=now + REFUSED_TTL,
                )
            )
        return await self._select(TeamJoinRequestRow.id.in_(ids))

    async def delete_for_team(self, team_id: str) -> None:
        async with use_session(self._sessions) as s:
            await s.execute(
                delete(TeamJoinRequestRow).where(TeamJoinRequestRow.team_id == team_id)
            )

    async def delete_for_requester(self, requester_id: str) -> list[str]:
        """Returns the deleted ids, so their notifications can go too."""
        async with use_session(self._sessions) as s:
            ids = list(
                (
                    await s.execute(
                        select(TeamJoinRequestRow.id).where(
                            TeamJoinRequestRow.requester_id == requester_id
                        )
                    )
                ).scalars()
            )
            if ids:
                await s.execute(
                    delete(TeamJoinRequestRow).where(TeamJoinRequestRow.id.in_(ids))
                )
            return ids

    async def delete_expired(self, *, limit: int) -> int:
        expired = (
            select(TeamJoinRequestRow.id)
            .where(TeamJoinRequestRow.expires_at <= utcnow())
            .limit(limit)
        )
        async with use_session(self._sessions) as s:
            result = await s.execute(
                delete(TeamJoinRequestRow).where(TeamJoinRequestRow.id.in_(expired))
            )
            return _rowcount(result)


__all__ = [
    "ASK_AGAIN_DELAY",
    "JoinRequestStatus",
    "PENDING_TTL",
    "REFUSED_TTL",
    "StoredJoinRequest",
    "TeamJoinRequestStore",
    "request_group",
]
