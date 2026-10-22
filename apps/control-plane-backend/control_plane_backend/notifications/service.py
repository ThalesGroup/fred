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

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Resource,
    TeamPermission,
)
from pydantic import TypeAdapter

from control_plane_backend.notifications.schemas import (
    MAX_PAGE_SIZE,
    NotificationPage,
    NotificationPayload,
    NotificationSummary,
    NotificationType,
    NotificationTypeSetting,
    NotificationTypeSettings,
    NotificationView,
)
from control_plane_backend.notifications.store import (
    DisabledType,
    NotificationDraft,
    NotificationStore,
    PageCursor,
    StoredNotification,
)

logger = logging.getLogger(__name__)

_SYSTEM = KPIActor(type="system")
_VIEW: TypeAdapter[NotificationView] = TypeAdapter(NotificationView)


def _required_check(draft: NotificationDraft) -> tuple[str, str, TeamPermission] | None:
    """The (recipient, team, permission) to hold for `draft`; `None`: unfiltered."""
    permission = draft.payload.PERMISSION
    if draft.team_id is None or permission is None:
        return None
    return draft.recipient_id, draft.team_id, permission


class NotificationNotFound(Exception):
    """No unexpired notification with that id belongs to the caller."""


class InvalidNotificationCursor(ValueError):
    """The `before` cursor is not one this service produced."""


def display_name(user: KeycloakUser) -> str:
    """The name a notification shows for `user`."""
    full = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full or user.username


def _to_view(stored: StoredNotification) -> NotificationView:
    return _VIEW.validate_python(
        {
            "id": stored.id,
            "type": stored.type,
            "team_id": stored.team_id,
            "payload": stored.payload,
            "created_at": stored.created_at,
            "expires_at": stored.expires_at,
            "seen_at": stored.seen_at,
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

    async def notify(self, drafts: Sequence[NotificationDraft]) -> None:
        """Emit in one insert; on failure, logs ids only."""
        try:
            disabled = await self._store.disabled_types()
            drafts = [d for d in drafts if d.payload.TYPE.value not in disabled]
            drafts = await self._allowed_recipients(drafts)
            if not drafts:
                return
            await self._store.upsert(drafts)
        except Exception:
            logger.warning(
                "Failed to emit notifications type=%s group_keys=%s",
                sorted({draft.payload.TYPE.value for draft in drafts}),
                sorted({draft.group_key for draft in drafts}),
                exc_info=True,
            )
            self._count("notifications.emit_failed_total", {"status": "error"})
            return
        for draft in drafts:
            self._count(
                "notifications.created_total",
                {"notification_type": draft.payload.TYPE.value},
            )

    async def _allowed_recipients(
        self, drafts: Sequence[NotificationDraft]
    ) -> Sequence[NotificationDraft]:
        """A team's notification only reaches who can act on it now."""
        if self._get_rebac is None:
            return drafts
        rebac = self._get_rebac()
        needed = [_required_check(d) for d in drafts]
        checks = sorted({check for check in needed if check is not None})
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
            d for d, check in zip(drafts, needed) if check is None or check in granted
        ]

    async def forget_lost_access(self, recipient_id: str, team_id: str) -> None:
        """After a role change, drop the open notifications about `team_id` that
        `recipient_id` may no longer receive. Best effort, never raises."""
        if self._get_rebac is None:
            return
        try:
            rebac = self._get_rebac()
            rules = {
                p.TYPE.value: p.PERMISSION for p in NotificationPayload.__subclasses__()
            }
            permissions = sorted({p for p in rules.values() if p is not None})
            held = await rebac.has_permissions(
                RebacReference(Resource.USER, recipient_id),
                permissions,
                RebacReference(Resource.TEAM, team_id),
                consistency_token=RebacEngine.HIGHER_CONSISTENCY,
            )
            lost = {p for p, ok in zip(permissions, held) if not ok}
            types = [t for t, p in rules.items() if p in lost]
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
        include_handled: bool = False,
    ) -> None:
        """The actor's own rows disappear; the other recipients see who handled it."""
        try:
            await self._store.resolve(
                group_keys,
                actor_uid=actor_uid,
                actor_name=actor_name,
                outcome=outcome,
                include_handled=include_handled,
            )
        except Exception:
            logger.warning(
                "Failed to resolve notifications group_keys=%s",
                sorted(group_keys),
                exc_info=True,
            )
            self._count("notifications.emit_failed_total", {"status": "error"})

    async def delete_groups(self, group_keys: Sequence[str]) -> None:
        """Every row of these groups goes, for every recipient (the subject is gone)."""
        try:
            await self._store.delete_groups(group_keys)
        except Exception:
            logger.warning(
                "Failed to delete notifications group_keys=%s",
                sorted(group_keys),
                exc_info=True,
            )

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

    async def delete(self, user: KeycloakUser, notification_id: str) -> None:
        if not await self._store.delete(user.uid, notification_id):
            raise NotificationNotFound(notification_id)

    async def clear(self, user: KeycloakUser) -> None:
        await self._store.delete_all(user.uid)

    # --- platform settings ------------------------------------------------------

    async def _require_manage_platform(self, user: KeycloakUser) -> None:
        # Same platform gate as the UI theme and announcement settings.
        if self._get_rebac is None:
            raise RuntimeError("platform settings need a ReBAC engine")
        await self._get_rebac().check_user_permission_or_raise(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )

    async def list_type_settings(self, user: KeycloakUser) -> NotificationTypeSettings:
        await self._require_manage_platform(user)
        disabled = await self._store.disabled_types()
        return NotificationTypeSettings(
            items=[
                _setting(type_, disabled.get(type_.value)) for type_ in NotificationType
            ]
        )

    async def set_type_enabled(
        self, user: KeycloakUser, type_: NotificationType, enabled: bool
    ) -> NotificationTypeSetting:
        """Off deletes every sent notification of the type for everyone; back on
        only affects new events."""
        await self._require_manage_platform(user)
        deleted = 0
        if enabled:
            await self._store.enable_type(type_.value)
        else:
            deleted = await self._store.disable_type(type_.value, disabled_by=user.uid)
        emit_audit_log(
            "platform.notification_type.updated",
            actor_uid=user.uid,
            notification_type=type_.value,
            enabled=enabled,
            deleted_notifications=deleted,
        )
        disabled = await self._store.disabled_types()
        return _setting(type_, disabled.get(type_.value))


def _setting(
    type_: NotificationType, disabled: DisabledType | None
) -> NotificationTypeSetting:
    if disabled is None:
        return NotificationTypeSetting(type=type_, enabled=True)
    return NotificationTypeSetting(
        type=type_,
        enabled=False,
        disabled_by=disabled.disabled_by,
        disabled_at=disabled.disabled_at,
    )


__all__ = [
    "InvalidNotificationCursor",
    "NotificationNotFound",
    "NotificationService",
    "display_name",
]
