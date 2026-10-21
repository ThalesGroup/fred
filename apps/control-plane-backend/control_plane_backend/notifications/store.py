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

"""Storage of notifications. No authorization here: every caller-facing method
takes the recipient and only ever touches that recipient's unexpired rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import CursorResult, and_, delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.notification_models import NotificationRow

#: How long a notification lives after its creation.
NOTIFICATION_TTL = timedelta(days=30)


@dataclass(frozen=True)
class NotificationDraft:
    """One notification to emit, before it has an id."""

    recipient_id: str
    type: str
    group_key: str
    payload: dict[str, Any]
    team_id: str | None = None


@dataclass(frozen=True)
class StoredNotification:
    id: str
    recipient_id: str
    type: str
    team_id: str | None
    group_key: str
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    seen_at: datetime | None
    read_at: datetime | None
    handled_at: datetime | None
    handled_by: str | None
    handled_by_name: str | None
    handled_outcome: str | None


@dataclass(frozen=True)
class PageCursor:
    created_at: datetime
    id: str

    def encode(self) -> str:
        return f"{_micros(self.created_at)}.{self.id}"

    @staticmethod
    def decode(value: str) -> PageCursor:
        """Raises `ValueError` on anything `encode` did not produce."""
        micros, _, notification_id = value.partition(".")
        if not notification_id:
            raise ValueError("malformed cursor")
        created_at = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=int(micros)
        )
        return PageCursor(created_at=created_at, id=notification_id)


def _aware(value: datetime) -> datetime:
    # SQLite hands timestamps back naive; they were written in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _micros(value: datetime) -> int:
    delta = _aware(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta // timedelta(microseconds=1)


def _to_stored(row: NotificationRow) -> StoredNotification:
    return StoredNotification(
        id=row.id,
        recipient_id=row.recipient_id,
        type=row.type,
        team_id=row.team_id,
        group_key=row.group_key,
        payload=dict(row.payload),
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        seen_at=row.seen_at and _aware(row.seen_at),
        read_at=row.read_at and _aware(row.read_at),
        handled_at=row.handled_at and _aware(row.handled_at),
        handled_by=row.handled_by,
        handled_by_name=row.handled_by_name,
        handled_outcome=row.handled_outcome,
    )


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount


def _up_to(cursor: PageCursor) -> Any:
    """Rows at or before `cursor` in list order (created_at, id)."""
    return or_(
        NotificationRow.created_at < cursor.created_at,
        and_(
            NotificationRow.created_at == cursor.created_at,
            NotificationRow.id <= cursor.id,
        ),
    )


class NotificationStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    def _mine(self, recipient_id: str, now: datetime) -> list[Any]:
        return [
            NotificationRow.recipient_id == recipient_id,
            NotificationRow.expires_at > now,
        ]

    async def upsert(self, drafts: Sequence[NotificationDraft]) -> int:
        """Insert in one statement; an open row of the same recipient and group
        gets the new payload and keeps its seen and read state."""
        # One row per (recipient, group): a statement may not update a row twice.
        unique = list({(d.recipient_id, d.group_key): d for d in drafts}.values())
        if not unique:
            return 0
        now = utcnow()
        keys = [(d.group_key, d.recipient_id) for d in unique]
        insert = (
            pg_insert if self._engine.dialect.name == "postgresql" else sqlite_insert
        )
        statement = insert(NotificationRow).values(
            [
                {
                    "id": str(uuid.uuid4()),
                    "recipient_id": d.recipient_id,
                    "type": d.type,
                    "team_id": d.team_id,
                    "group_key": d.group_key,
                    "payload": d.payload,
                    "created_at": now,
                    "expires_at": now + NOTIFICATION_TTL,
                }
                for d in unique
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[NotificationRow.group_key, NotificationRow.recipient_id],
            index_where=NotificationRow.handled_at.is_(None),
            set_={
                "type": statement.excluded.type,
                "team_id": statement.excluded.team_id,
                "payload": statement.excluded.payload,
            },
        )
        async with use_session(self._sessions) as s:
            # An expired open row is invisible: replace it rather than update it.
            await s.execute(
                delete(NotificationRow).where(
                    tuple_(NotificationRow.group_key, NotificationRow.recipient_id).in_(
                        keys
                    ),
                    NotificationRow.handled_at.is_(None),
                    NotificationRow.expires_at <= now,
                )
            )
            await s.execute(statement)
        return len(unique)

    async def resolve(
        self,
        group_keys: Sequence[str],
        *,
        actor_uid: str | None,
        actor_name: str | None,
        outcome: str,
    ) -> None:
        """The actor's own open rows go; every other open row is marked handled."""
        if not group_keys:
            return
        open_rows = [
            NotificationRow.group_key.in_(list(group_keys)),
            NotificationRow.handled_at.is_(None),
        ]
        async with use_session(self._sessions) as s:
            if actor_uid is not None:
                await s.execute(
                    delete(NotificationRow).where(
                        *open_rows, NotificationRow.recipient_id == actor_uid
                    )
                )
            await s.execute(
                update(NotificationRow)
                .where(*open_rows)
                .values(
                    handled_at=utcnow(),
                    handled_by=actor_uid,
                    handled_by_name=actor_name,
                    handled_outcome=outcome,
                )
            )

    async def unseen_count(self, recipient_id: str) -> int:
        async with use_session(self._sessions) as s:
            return (
                await s.execute(
                    select(func.count()).where(
                        *self._mine(recipient_id, utcnow()),
                        NotificationRow.seen_at.is_(None),
                    )
                )
            ).scalar_one()

    async def list_page(
        self, recipient_id: str, *, limit: int, before: PageCursor | None = None
    ) -> tuple[list[StoredNotification], PageCursor | None]:
        """Newest first; the cursor is set when an older row remains."""
        query = select(NotificationRow).where(*self._mine(recipient_id, utcnow()))
        if before is not None:
            query = query.where(
                or_(
                    NotificationRow.created_at < before.created_at,
                    and_(
                        NotificationRow.created_at == before.created_at,
                        NotificationRow.id < before.id,
                    ),
                )
            )
        query = query.order_by(
            NotificationRow.created_at.desc(), NotificationRow.id.desc()
        ).limit(limit + 1)
        async with use_session(self._sessions) as s:
            rows = [_to_stored(row) for row in (await s.execute(query)).scalars()]
        if len(rows) <= limit:
            return rows, None
        last = rows[limit - 1]
        return rows[:limit], PageCursor(created_at=last.created_at, id=last.id)

    async def mark_seen(self, recipient_id: str, up_to_id: str) -> bool:
        """Mark seen every row at or before `up_to_id`; `False` if it is not theirs."""
        now = utcnow()
        async with use_session(self._sessions) as s:
            created_at = (
                await s.execute(
                    select(NotificationRow.created_at).where(
                        *self._mine(recipient_id, now), NotificationRow.id == up_to_id
                    )
                )
            ).scalar_one_or_none()
            if created_at is None:
                return False
            await s.execute(
                update(NotificationRow)
                .where(
                    *self._mine(recipient_id, now),
                    NotificationRow.seen_at.is_(None),
                    _up_to(PageCursor(created_at=created_at, id=up_to_id)),
                )
                .values(seen_at=now)
            )
            return True

    async def mark_read(self, recipient_id: str, notification_id: str) -> bool:
        now = utcnow()
        async with use_session(self._sessions) as s:
            result = await s.execute(
                update(NotificationRow)
                .where(
                    *self._mine(recipient_id, now),
                    NotificationRow.id == notification_id,
                )
                .values(
                    read_at=func.coalesce(NotificationRow.read_at, now),
                    seen_at=func.coalesce(NotificationRow.seen_at, now),
                )
            )
            return _rowcount(result) > 0

    async def delete(self, recipient_id: str, notification_id: str) -> bool:
        async with use_session(self._sessions) as s:
            result = await s.execute(
                delete(NotificationRow).where(
                    *self._mine(recipient_id, utcnow()),
                    NotificationRow.id == notification_id,
                )
            )
            return _rowcount(result) > 0

    async def delete_all(self, recipient_id: str) -> int:
        async with use_session(self._sessions) as s:
            result = await s.execute(
                delete(NotificationRow).where(
                    NotificationRow.recipient_id == recipient_id
                )
            )
            return _rowcount(result)

    async def delete_expired(self, *, limit: int) -> int:
        """Delete at most `limit` expired rows; returns how many went."""
        expired = (
            select(NotificationRow.id)
            .where(NotificationRow.expires_at <= utcnow())
            .limit(limit)
        )
        async with use_session(self._sessions) as s:
            result = await s.execute(
                delete(NotificationRow).where(NotificationRow.id.in_(expired))
            )
            return _rowcount(result)

    async def delete_for_user(self, recipient_id: str) -> None:
        await self.delete_all(recipient_id)

    async def delete_for_team(self, team_id: str) -> None:
        async with use_session(self._sessions) as s:
            await s.execute(
                delete(NotificationRow).where(NotificationRow.team_id == team_id)
            )


__all__ = [
    "NOTIFICATION_TTL",
    "NotificationDraft",
    "NotificationStore",
    "PageCursor",
    "StoredNotification",
]
