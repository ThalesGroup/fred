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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.announcement_models import AnnouncementRow
from control_plane_backend.models.base import utcnow


@dataclass(frozen=True)
class StoredAnnouncement:
    """One stored announcement row."""

    id: str
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


def _to_stored(row: AnnouncementRow) -> StoredAnnouncement:
    return StoredAnnouncement(
        id=row.id,
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
        """The enabled announcements, oldest first.

        Ordered by creation here so the delivery route is deterministic on its
        own; severity ordering is the client's, since it is presentation.
        """
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow)
                    .where(AnnouncementRow.enabled.is_(True))
                    .order_by(
                        AnnouncementRow.created_at.asc(), AnnouncementRow.id.asc()
                    )
                )
            ).scalars()
            return [_to_stored(row) for row in rows]

    async def get(
        self, announcement_id: str, *, session: AsyncSession | None = None
    ) -> StoredAnnouncement | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(AnnouncementRow).where(AnnouncementRow.id == announcement_id)
                )
            ).scalar_one_or_none()
            return None if row is None else _to_stored(row)

    async def create(
        self,
        *,
        announcement_id: str,
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
        enabled: bool,
        dismissible: bool,
        content_version: int,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredAnnouncement | None:
        """Overwrite every mutable field. Returns `None` if the row is gone."""
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
            row.enabled = enabled
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
            await s.delete(row)
            return True


__all__ = ["AnnouncementStore", "StoredAnnouncement"]
