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

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.announcement_models import (
    AnnouncementActivationEventRow,
    AnnouncementDismissalRow,
    AnnouncementRow,
)
from control_plane_backend.models.base import utcnow


@dataclass(frozen=True)
class StoredAnnouncement:
    """One stored announcement row."""

    id: str
    kind: str
    severity: str
    title: dict[str, str]
    description_short: dict[str, str]
    description_long: dict[str, str]
    enabled: bool
    dismissible: bool
    content_version: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None


@dataclass(frozen=True)
class StoredActivationEvent:
    """One row of the append-only activation history."""

    id: str
    announcement_id: str
    kind: str
    label: dict[str, str]
    action: str
    actor_uid: str | None
    occurred_at: datetime
    severity: str | None = None


def _to_stored(row: AnnouncementRow) -> StoredAnnouncement:
    return StoredAnnouncement(
        id=row.id,
        kind=row.kind,
        severity=row.severity,
        title=dict(row.title),
        description_short=dict(row.description_short),
        description_long=dict(row.description_long),
        enabled=row.enabled,
        dismissible=row.dismissible,
        content_version=row.content_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


class AnnouncementStore:
    """Pure CRUD over ``platform_announcement``.

    Same separation of concerns as `PlatformPromptStore`: this store never
    checks authorization, that is `announcements/service.py`'s job, and it never
    decides when `content_version` moves — callers pass the value they want
    written, so the rule for when it moves lives in one place instead of being
    split across two layers.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """One committed-or-rolled-back session to pass to several calls."""
        async with use_session(self._sessions) as s:
            yield s

    async def list_all(
        self, *, session: AsyncSession | None = None
    ) -> list[StoredAnnouncement]:
        """Every announcement, newest first — the admin page's listing."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow).order_by(
                        AnnouncementRow.created_at.desc(), AnnouncementRow.id.desc()
                    )
                )
            ).scalars()
            return [_to_stored(row) for row in rows]

    async def list_enabled(
        self, *, session: AsyncSession | None = None
    ) -> list[StoredAnnouncement]:
        """The enabled banners, oldest first. Patch notes have their own read.

        Ordered by creation here so the delivery route is deterministic on its
        own; severity ordering is the client's, since it is presentation.
        """
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow)
                    .where(
                        AnnouncementRow.enabled.is_(True),
                        AnnouncementRow.kind == "banner",
                    )
                    .order_by(
                        AnnouncementRow.created_at.asc(), AnnouncementRow.id.asc()
                    )
                )
            ).scalars()
            return [_to_stored(row) for row in rows]

    async def get(
        self,
        announcement_id: str,
        *,
        for_update: bool = False,
        session: AsyncSession | None = None,
    ) -> StoredAnnouncement | None:
        """`for_update` locks the row until the transaction ends (no-op on SQLite)."""
        query = select(AnnouncementRow).where(AnnouncementRow.id == announcement_id)
        if for_update:
            query = query.with_for_update()
        async with use_session(self._sessions, session) as s:
            row = (await s.execute(query)).scalar_one_or_none()
            return None if row is None else _to_stored(row)

    async def create(
        self,
        *,
        announcement_id: str,
        kind: str = "banner",
        severity: str,
        title: dict[str, str],
        description_short: dict[str, str],
        description_long: dict[str, str],
        enabled: bool,
        dismissible: bool,
        created_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredAnnouncement:
        async with use_session(self._sessions, session) as s:
            row = AnnouncementRow(
                id=announcement_id,
                kind=kind,
                severity=severity,
                title=title,
                description_short=description_short,
                description_long=description_long,
                enabled=enabled,
                dismissible=dismissible,
                content_version=1,
                created_by=created_by,
                updated_by=created_by,
            )
            s.add(row)
            # Flush so the Python-side `default` callables (utcnow) populate the
            # timestamps before this method reads them back, same reasoning as
            # `PlatformPromptStore.set`.
            await s.flush()
            return _to_stored(row)

    async def update(
        self,
        *,
        announcement_id: str,
        severity: str,
        title: dict[str, str],
        description_short: dict[str, str],
        description_long: dict[str, str],
        dismissible: bool,
        content_version: int,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredAnnouncement | None:
        """Overwrite the content fields. Returns `None` if the row is gone.

        `enabled` is not one of them: only `set_enabled` changes delivery.
        """
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(AnnouncementRow).where(AnnouncementRow.id == announcement_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.severity = severity
            row.title = title
            row.description_short = description_short
            row.description_long = description_long
            row.dismissible = dismissible
            row.content_version = content_version
            row.updated_by = updated_by
            # Explicit, not `onupdate`: re-saving an identical announcement
            # leaves SQLAlchemy seeing no dirty attribute and emitting no
            # UPDATE, which would keep reporting the previous save on the admin
            # page. Same fix as `PlatformPromptStore.set`.
            row.updated_at = utcnow()
            await s.flush()
            return _to_stored(row)

    async def set_enabled(
        self,
        *,
        announcement_id: str,
        enabled: bool,
        content_version: int,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredAnnouncement | None:
        """Toggle delivery, writing the `content_version` the caller decided."""
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(AnnouncementRow).where(AnnouncementRow.id == announcement_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.enabled = enabled
            row.content_version = content_version
            row.updated_by = updated_by
            row.updated_at = utcnow()
            await s.flush()
            return _to_stored(row)

    async def delete(
        self, announcement_id: str, *, session: AsyncSession | None = None
    ) -> bool:
        """Remove the announcement. Returns whether a row was actually removed."""
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(AnnouncementRow).where(AnnouncementRow.id == announcement_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            # Explicit, not only ON DELETE CASCADE: SQLite does not enforce it.
            await self.delete_dismissals(announcement_id, session=s)
            await s.delete(row)
            return True

    async def get_enabled_patch_note(
        self, *, session: AsyncSession | None = None
    ) -> StoredAnnouncement | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(AnnouncementRow).where(
                        AnnouncementRow.enabled.is_(True),
                        AnnouncementRow.kind == "patch_note",
                    )
                )
            ).scalar_one_or_none()
            return None if row is None else _to_stored(row)

    async def disable_other_patch_notes(
        self,
        *,
        except_id: str,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> list[StoredAnnouncement]:
        """Disable every enabled patch note but `except_id`; return them as stored before."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow).where(
                        AnnouncementRow.enabled.is_(True),
                        AnnouncementRow.kind == "patch_note",
                        AnnouncementRow.id != except_id,
                    )
                )
            ).scalars()
            disabled: list[StoredAnnouncement] = []
            for row in rows:
                disabled.append(_to_stored(row))
                row.enabled = False
                row.updated_by = updated_by
                row.updated_at = utcnow()
            # Flush now so the target's enable cannot hit the partial index first.
            await s.flush()
            return disabled

    async def append_activation_events(
        self,
        events: Sequence[StoredActivationEvent],
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Append history rows. There is deliberately no update or delete."""
        if not events:
            return
        async with use_session(self._sessions, session) as s:
            s.add_all(
                AnnouncementActivationEventRow(
                    id=event.id,
                    announcement_id=event.announcement_id,
                    kind=event.kind,
                    label=event.label,
                    severity=event.severity,
                    action=event.action,
                    actor_uid=event.actor_uid,
                    occurred_at=event.occurred_at,
                )
                for event in events
            )
            await s.flush()

    async def list_activation_events(
        self, *, limit: int, session: AsyncSession | None = None
    ) -> list[StoredActivationEvent]:
        """The newest `limit` events, newest first."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementActivationEventRow)
                    .order_by(
                        AnnouncementActivationEventRow.occurred_at.desc(),
                        AnnouncementActivationEventRow.id.desc(),
                    )
                    .limit(limit)
                )
            ).scalars()
            return [
                StoredActivationEvent(
                    id=row.id,
                    announcement_id=row.announcement_id,
                    kind=row.kind,
                    label=dict(row.label),
                    severity=row.severity,
                    action=row.action,
                    actor_uid=row.actor_uid,
                    occurred_at=row.occurred_at,
                )
                for row in rows
            ]

    async def add_dismissal(
        self,
        *,
        announcement_id: str,
        user_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Record `user_id`'s dismissal of that note; idempotent."""
        try:
            async with use_session(self._sessions, session) as s:
                row = await s.get(AnnouncementDismissalRow, (announcement_id, user_id))
                if row is None:
                    s.add(
                        AnnouncementDismissalRow(
                            announcement_id=announcement_id, user_id=user_id
                        )
                    )
                else:
                    row.dismissed_at = utcnow()
        except IntegrityError:
            # Only a concurrent duplicate is benign; a note deleted meanwhile
            # (foreign key) must surface to the caller.
            if session is not None or not await self.is_dismissed(
                announcement_id=announcement_id, user_id=user_id
            ):
                raise

    async def is_dismissed(
        self,
        *,
        announcement_id: str,
        user_id: str,
        session: AsyncSession | None = None,
    ) -> bool:
        async with use_session(self._sessions, session) as s:
            return (
                await s.get(AnnouncementDismissalRow, (announcement_id, user_id))
            ) is not None

    async def count_dismissals(
        self, *, session: AsyncSession | None = None
    ) -> dict[str, int]:
        """Per announcement id, how many users dismissed it."""
        async with use_session(self._sessions, session) as s:
            rows = await s.execute(
                select(AnnouncementDismissalRow.announcement_id, func.count()).group_by(
                    AnnouncementDismissalRow.announcement_id
                )
            )
            return {announcement_id: count for announcement_id, count in rows.all()}

    async def delete_dismissals(
        self, announcement_id: str, *, session: AsyncSession | None = None
    ) -> None:
        """Drop every user's dismissal of `announcement_id` (re-enable)."""
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(AnnouncementDismissalRow).where(
                    AnnouncementDismissalRow.announcement_id == announcement_id
                )
            )

    async def delete_dismissals_for_user(
        self, user_id: str, *, session: AsyncSession | None = None
    ) -> None:
        """Drop every patch-note dismissal of `user_id` (account deletion)."""
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(AnnouncementDismissalRow).where(
                    AnnouncementDismissalRow.user_id == user_id
                )
            )


__all__ = ["AnnouncementStore", "StoredActivationEvent", "StoredAnnouncement"]
