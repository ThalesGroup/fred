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

"""Emit, resolve and read notifications.

Domain services call `notify`/`resolve` after their own commit. Both are best
effort: a failure is logged with ids only and counted, never raised.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any

from fred_core import KeycloakUser
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacReference,
    Resource,
    TeamPermission,
)
from pydantic import BaseModel, TypeAdapter

from control_plane_backend.notifications.schemas import (
    ACTION_PERMISSION,
    MAX_PAGE_SIZE,
    NotificationPage,
    NotificationSummary,
    NotificationType,
    NotificationView,
    validate_payload,
)
from control_plane_backend.notifications.store import (
    NotificationDraft,
    NotificationStore,
    PageCursor,
    StoredNotification,
)

logger = logging.getLogger(__name__)

_SYSTEM = KPIActor(type="system")
_VIEW: TypeAdapter[Any] = TypeAdapter(NotificationView)


def _required_permission(type_: str) -> TeamPermission:
    return ACTION_PERMISSION[NotificationType(type_)]


class NotificationNotFound(Exception):
    """No unexpired notification with that id belongs to the caller."""


class InvalidNotificationCursor(ValueError):
    """The `before` cursor is not one this service produced."""


def display_name(user: KeycloakUser) -> str:
    """The name a notification shows for `user`."""
    full = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full or user.username


def _to_view(stored: StoredNotification) -> Any:
    return _VIEW.validate_python(
        {
            "id": stored.id,
            "type": stored.type,
            "team_id": stored.team_id,
            "payload": stored.payload,
            "created_at": stored.created_at,
            "expires_at": stored.expires_at,
            "seen_at": stored.seen_at,
            "read_at": stored.read_at,
            "handled_at": stored.handled_at,
            "handled_by_name": stored.handled_by_name,
            "handled_outcome": stored.handled_outcome,
        }
    )


class NotificationService:
    def __init__(
        self,
        store: NotificationStore,
        get_kpi_writer: Callable[[], BaseKPIWriter] | None = None,
        get_rebac: Callable[[], RebacEngine] | None = None,
    ) -> None:
        self._store = store
        self._get_kpi_writer = get_kpi_writer
        # None = no membership filter (tests that do not model teams).
        self._get_rebac = get_rebac

    @property
    def store(self) -> NotificationStore:
        return self._store

    def _count(self, name: str, dims: dict[str, str | None]) -> None:
        if self._get_kpi_writer is None:
            return
        try:
            self._get_kpi_writer().count(name, dims=dims, actor=_SYSTEM)
        except Exception:
            logger.exception("Failed to emit %s", name)

    async def notify(
        self,
        *,
        recipients: Sequence[str],
        type: NotificationType,
        payload: BaseModel | dict[str, Any],
        group_key: str,
        team_id: str | None = None,
    ) -> bool:
        """One notification per recipient; see `notify_many`."""
        try:
            stored = validate_payload(type, payload)
        except Exception:
            # A programming error, still never the triggering action's failure.
            logger.warning("Invalid notification payload type=%s", type.value)
            self._count("notifications.emit_failed_total", {"status": "invalid"})
            return False
        return await self.notify_many(
            [
                NotificationDraft(
                    recipient_id=recipient,
                    type=type.value,
                    group_key=group_key,
                    payload=stored,
                    team_id=team_id,
                )
                for recipient in recipients
            ]
        )

    async def notify_many(self, drafts: Sequence[NotificationDraft]) -> bool:
        """Emit in one insert. Returns `False`, logging ids only, on failure."""
        if not drafts:
            return True
        try:
            for draft in drafts:
                validate_payload(draft.type, draft.payload)
            drafts = await self._allowed_recipients(drafts)
            if not drafts:
                return True
            await self._store.upsert(drafts)
        except Exception:
            logger.warning(
                "Failed to emit notifications type=%s group_keys=%s",
                sorted({draft.type for draft in drafts}),
                sorted({draft.group_key for draft in drafts}),
                exc_info=True,
            )
            self._count("notifications.emit_failed_total", {"status": "error"})
            return False
        for draft in drafts:
            self._count(
                "notifications.created_total", {"notification_type": draft.type}
            )
        return True

    async def _allowed_recipients(
        self, drafts: Sequence[NotificationDraft]
    ) -> Sequence[NotificationDraft]:
        """A team's notification only reaches who can act on it now."""
        if self._get_rebac is None:
            return drafts
        rebac = self._get_rebac()
        checks = sorted(
            {
                (d.recipient_id, d.team_id, _required_permission(d.type))
                for d in drafts
                if d.team_id is not None
            }
        )
        allowed = await asyncio.gather(
            *(
                rebac.has_permission(
                    RebacReference(Resource.USER, uid),
                    permission,
                    RebacReference(Resource.TEAM, team_id),
                )
                for uid, team_id, permission in checks
            )
        )
        granted = {check for check, ok in zip(checks, allowed) if ok}
        return [
            d
            for d in drafts
            if d.team_id is None
            or (d.recipient_id, d.team_id, _required_permission(d.type)) in granted
        ]

    async def forget_lost_access(self, recipient_id: str, team_id: str) -> None:
        """After a role change, drop the open notifications about `team_id` that
        `recipient_id` may no longer receive. Best effort, never raises."""
        if self._get_rebac is None:
            return
        try:
            rebac = self._get_rebac()
            permissions = sorted(set(ACTION_PERMISSION.values()))
            held = await rebac.has_permissions(
                RebacReference(Resource.USER, recipient_id),
                permissions,
                RebacReference(Resource.TEAM, team_id),
                consistency_token=RebacEngine.HIGHER_CONSISTENCY,
            )
            lost = {p for p, ok in zip(permissions, held) if not ok}
            types = [t.value for t, p in ACTION_PERMISSION.items() if p in lost]
            if types:
                await self._store.delete_for_member(recipient_id, team_id, types=types)
        except Exception:
            logger.warning(
                "Failed to drop notifications recipient_id=%s team_id=%s",
                recipient_id,
                team_id,
                exc_info=True,
            )

    async def resolve(
        self,
        group_keys: Sequence[str],
        *,
        actor_uid: str | None,
        actor_name: str | None,
        outcome: str,
    ) -> bool:
        """The actor's own rows disappear; the other recipients see who handled it."""
        try:
            await self._store.resolve(
                group_keys, actor_uid=actor_uid, actor_name=actor_name, outcome=outcome
            )
        except Exception:
            logger.warning(
                "Failed to resolve notifications group_keys=%s",
                sorted(group_keys),
                exc_info=True,
            )
            self._count("notifications.emit_failed_total", {"status": "error"})
            return False
        return True

    async def summary(self, user: KeycloakUser) -> NotificationSummary:
        return NotificationSummary(
            unseen_count=await self._store.unseen_count(user.uid)
        )

    async def list_page(
        self, user: KeycloakUser, *, limit: int, before: str | None
    ) -> NotificationPage:
        try:
            cursor = PageCursor.decode(before) if before else None
        except ValueError as exc:
            raise InvalidNotificationCursor(str(exc)) from exc
        rows, next_cursor = await self._store.list_page(
            user.uid, limit=min(limit, MAX_PAGE_SIZE), before=cursor
        )
        items = []
        for row in rows:
            try:
                items.append(_to_view(row))
            except ValueError:
                # A type this version does not know (left by a newer one).
                logger.warning("Skipping notification id=%s type=%s", row.id, row.type)
        return NotificationPage(
            items=items,
            next_cursor=next_cursor.encode() if next_cursor else None,
        )

    async def mark_seen(self, user: KeycloakUser, up_to: str) -> NotificationSummary:
        if not await self._store.mark_seen(user.uid, up_to):
            raise NotificationNotFound(up_to)
        return await self.summary(user)

    async def mark_read(self, user: KeycloakUser, notification_id: str) -> None:
        if not await self._store.mark_read(user.uid, notification_id):
            raise NotificationNotFound(notification_id)

    async def delete(self, user: KeycloakUser, notification_id: str) -> None:
        if not await self._store.delete(user.uid, notification_id):
            raise NotificationNotFound(notification_id)

    async def clear(self, user: KeycloakUser) -> None:
        await self._store.delete_all(user.uid)


__all__ = [
    "InvalidNotificationCursor",
    "NotificationNotFound",
    "NotificationService",
    "display_name",
]
