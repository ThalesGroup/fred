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
from typing import Any, cast

from fred_core.sql import make_session_factory, use_session
from fred_core.sql.base_sql import advisory_lock_key
from sqlalchemy import (
    CursorResult,
    DateTime,
    delete,
    literal,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import aliased, undefer

from control_plane_backend.models.announcement_models import (
    AnnouncementExposureRow,
    AnnouncementRow,
    AnnouncementSeenRow,
)
from control_plane_backend.models.base import utcnow

_PATCH_NOTES_LOCK = "platform_announcement:patch_notes"


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
    position: int | None = None


@dataclass(frozen=True)
class StoredExposure:
    """One exposure row. `package` is only loaded where a caller asks for it."""

    id: str
    kind: str
    announcement_id: str
    label: dict[str, str]
    actor_uid: str | None
    activated_at: datetime
    deactivated_at: datetime | None = None
    severity: str | None = None
    note_count: int | None = None
    opens_dialog: bool = True
    package: list[dict[str, Any]] | None = None


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
        position=row.position,
    )


def _to_stored_exposure(
    row: AnnouncementExposureRow, *, with_package: bool = False
) -> StoredExposure:
    return StoredExposure(
        id=row.id,
        kind=row.kind,
        announcement_id=row.announcement_id,
        label=dict(row.label),
        actor_uid=row.actor_uid,
        activated_at=row.activated_at,
        deactivated_at=row.deactivated_at,
        severity=row.severity,
        note_count=row.note_count,
        opens_dialog=row.opens_dialog,
        # Deferred column: only touch it when the query loaded it.
        package=row.package if with_package else None,
    )


def _is_patch_note():
    return AnnouncementRow.kind == "patch_note"


class AnnouncementStore:
    """Pure CRUD over ``platform_announcement``.

    Same separation of concerns as `PlatformPromptStore`: this store never
    checks authorization, that is `announcements/service.py`'s job, and it never
    decides when `content_version` moves — callers pass the value they want
    written, so the rule for when it moves lives in one place instead of being
    split across two layers.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """One committed-or-rolled-back session to pass to several calls."""
        async with use_session(self._sessions) as s:
            yield s

    async def lock_patch_notes(self, *, session: AsyncSession) -> None:
        """Serialize the writes that order or announce patch notes, until the
        transaction ends. Postgres advisory lock; a no-op on SQLite, which
        already allows one writer at a time."""
        if self._engine.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": advisory_lock_key(_PATCH_NOTES_LOCK)},
            )

    async def list_all(
        self, *, session: AsyncSession | None = None
    ) -> list[StoredAnnouncement]:
        """The admin page's listing: banners newest first, then patch notes
        in the administrator's order."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow).order_by(
                        AnnouncementRow.position.asc().nulls_first(),
                        AnnouncementRow.created_at.desc(),
                        AnnouncementRow.id.desc(),
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
            position = None
            if kind == "patch_note":
                # Locked so a reorder under way cannot reuse the top place.
                await self.lock_patch_notes(session=s)
                # A new patch note takes the top place; the others move down.
                await s.execute(
                    update(AnnouncementRow)
                    .where(_is_patch_note())
                    .values(position=AnnouncementRow.position + 1)
                )
                position = 1
            row = AnnouncementRow(
                id=announcement_id,
                kind=kind,
                position=position,
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
            await s.delete(row)
            return True

    async def list_included_patch_notes(
        self, *, session: AsyncSession | None = None
    ) -> list[StoredAnnouncement]:
        """The enabled patch notes in the administrator's order: what the next
        announcement will freeze."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementRow)
                    .where(AnnouncementRow.enabled.is_(True), _is_patch_note())
                    .order_by(
                        AnnouncementRow.position.asc(),
                        AnnouncementRow.created_at.desc(),
                        AnnouncementRow.id.desc(),
                    )
                )
            ).scalars()
            return [_to_stored(row) for row in rows]

    async def set_patch_note_order(
        self, ordered_ids: Sequence[str], *, session: AsyncSession | None = None
    ) -> bool:
        """Rewrite every patch note's position to follow `ordered_ids`.

        Returns `False`, changing nothing, unless the list names each existing
        patch note exactly once.
        """
        async with use_session(self._sessions, session) as s:
            await self.lock_patch_notes(session=s)
            rows = {
                row.id: row
                for row in (
                    await s.execute(
                        select(AnnouncementRow)
                        .where(_is_patch_note())
                        .with_for_update()
                    )
                ).scalars()
            }
            if len(ordered_ids) != len(rows) or set(ordered_ids) != set(rows):
                return False
            for position, announcement_id in enumerate(ordered_ids, start=1):
                rows[announcement_id].position = position
            await s.flush()
            return True

    async def add_exposure(
        self, exposure: StoredExposure, *, session: AsyncSession | None = None
    ) -> None:
        """Start an exposure: one new history line."""
        async with use_session(self._sessions, session) as s:
            s.add(
                AnnouncementExposureRow(
                    id=exposure.id,
                    kind=exposure.kind,
                    announcement_id=exposure.announcement_id,
                    label=exposure.label,
                    severity=exposure.severity,
                    actor_uid=exposure.actor_uid,
                    activated_at=exposure.activated_at,
                    deactivated_at=exposure.deactivated_at,
                    note_count=exposure.note_count,
                    package=exposure.package,
                    opens_dialog=exposure.opens_dialog,
                )
            )
            await s.flush()

    async def end_exposures(
        self,
        *,
        kind: str,
        at: datetime,
        announcement_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> int:
        """End the open exposures of `kind` (of one announcement when given).

        Returns how many were open.
        """
        query = update(AnnouncementExposureRow).where(
            AnnouncementExposureRow.kind == kind,
            AnnouncementExposureRow.deactivated_at.is_(None),
        )
        if announcement_id is not None:
            query = query.where(
                AnnouncementExposureRow.announcement_id == announcement_id
            )
        async with use_session(self._sessions, session) as s:
            result = await s.execute(query.values(deactivated_at=at))
            return cast(CursorResult[Any], result).rowcount

    async def list_exposures(
        self, *, limit: int, session: AsyncSession | None = None
    ) -> list[StoredExposure]:
        """The newest `limit` exposures, newest first, without their packages."""
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(AnnouncementExposureRow)
                    .order_by(
                        AnnouncementExposureRow.activated_at.desc(),
                        AnnouncementExposureRow.id.desc(),
                    )
                    .limit(limit)
                )
            ).scalars()
            return [_to_stored_exposure(row) for row in rows]

    async def get_exposure(
        self,
        exposure_id: str,
        *,
        with_package: bool = False,
        session: AsyncSession | None = None,
    ) -> StoredExposure | None:
        query = select(AnnouncementExposureRow).where(
            AnnouncementExposureRow.id == exposure_id
        )
        if with_package:
            query = query.options(undefer(AnnouncementExposureRow.package))
        async with use_session(self._sessions, session) as s:
            row = (await s.execute(query)).scalar_one_or_none()
            if row is None:
                return None
            return _to_stored_exposure(row, with_package=with_package)

    async def get_announcement_in_effect(
        self, *, with_package: bool = False, session: AsyncSession | None = None
    ) -> StoredExposure | None:
        """The open patch-note exposure that holds a package, if any.

        The one definition of "an announcement is in effect": the users' read,
        the admin read and the withdrawal all go through it.
        """
        query = (
            select(AnnouncementExposureRow)
            .where(
                AnnouncementExposureRow.kind == "patch_note",
                AnnouncementExposureRow.deactivated_at.is_(None),
                AnnouncementExposureRow.note_count.is_not(None),
            )
            .order_by(
                AnnouncementExposureRow.activated_at.desc(),
                AnnouncementExposureRow.id.desc(),
            )
            .limit(1)
        )
        if with_package:
            query = query.options(undefer(AnnouncementExposureRow.package))
        async with use_session(self._sessions, session) as s:
            row = (await s.execute(query)).scalar_one_or_none()
            if row is None:
                return None
            return _to_stored_exposure(row, with_package=with_package)

    async def get_seen_announcement_id(
        self, user_id: str, *, session: AsyncSession | None = None
    ) -> str | None:
        """The announcement `user_id` last saw, if any."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(AnnouncementSeenRow, user_id)
            return None if row is None else row.announcement_id

    async def record_seen_announcement(
        self,
        *,
        user_id: str,
        announcement_id: str,
        session: AsyncSession | None = None,
    ) -> bool:
        """Record that `user_id` saw that announcement, in one statement.

        Returns `False`, writing nothing, when no announcement has that id or
        the user's record is already at it or at a more recent one.
        """
        seen = AnnouncementSeenRow.__table__
        target = aliased(AnnouncementExposureRow)
        recorded = aliased(AnnouncementExposureRow)
        insert = (
            pg_insert if self._engine.dialect.name == "postgresql" else sqlite_insert
        )
        statement = insert(AnnouncementSeenRow).from_select(
            ["user_id", "announcement_id", "seen_at"],
            select(
                literal(user_id),
                target.id,
                literal(utcnow(), type_=DateTime(timezone=True)),
            ).where(target.id == announcement_id, target.note_count.is_not(None)),
        )
        # Never backwards: a late close of an older dialog keeps the newer record.
        recorded_is_newer = (
            select(recorded.id)
            .where(
                # By name: a table object would be joined in, not correlated.
                recorded.id
                == literal_column(
                    f"{AnnouncementSeenRow.__tablename__}.announcement_id"
                ),
                recorded.activated_at
                > select(target.activated_at)
                .where(target.id == announcement_id)
                .scalar_subquery(),
            )
            .exists()
        )
        statement = statement.on_conflict_do_update(
            index_elements=[seen.c.user_id],
            set_={
                "announcement_id": statement.excluded.announcement_id,
                "seen_at": statement.excluded.seen_at,
            },
            where=(seen.c.announcement_id != announcement_id) & ~recorded_is_newer,
        )
        async with use_session(self._sessions, session) as s:
            result = await s.execute(statement)
            return cast(CursorResult[Any], result).rowcount > 0

    async def delete_seen_for_user(
        self, user_id: str, *, session: AsyncSession | None = None
    ) -> None:
        """Drop what `user_id` last saw (account deletion)."""
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(AnnouncementSeenRow).where(
                    AnnouncementSeenRow.user_id == user_id
                )
            )


__all__ = ["AnnouncementStore", "StoredAnnouncement", "StoredExposure"]
