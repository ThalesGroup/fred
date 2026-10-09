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

import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from fred_core import KeycloakUser, OrganizationPermission
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID
from sqlalchemy.exc import IntegrityError

from control_plane_backend.announcements.schemas import (
    ActivePatchNote,
    AdminAnnouncement,
    Announcement,
    AnnouncementActivationEvent,
    AnnouncementWriteRequest,
)
from control_plane_backend.announcements.store import (
    StoredActivationEvent,
    StoredAnnouncement,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.product.dependencies import ProductServiceDependencies

#: How many activation events the admin history returns (no pagination).
ACTIVATION_HISTORY_LIMIT = 100

_NOT_FOUND = "announcement not found"
_CONCURRENT_ACTIVATION = (
    "another patch note was activated at the same time; reload and retry"
)


async def _require_manage_platform(
    deps: ProductServiceDependencies, user: KeycloakUser
) -> None:
    """The catch-all platform gate, as the other admin-only surfaces use it.

    `organization_authz.py` deliberately keeps no helper for this one — the
    named helpers exist so a delegated surface cannot reuse the catch-all — so
    the check is spelled out here, the same way `main.py` spells it out for
    import/export, tasks and platform reset.
    """

    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


def _to_announcement(stored: StoredAnnouncement) -> Announcement:
    return Announcement(
        id=stored.id,
        kind=stored.kind,  # type: ignore[arg-type]
        severity=stored.severity,  # type: ignore[arg-type]
        title=stored.title,
        description_short=stored.description_short,
        description_long=stored.description_long,
        enabled=stored.enabled,
        dismissible=stored.dismissible,
        content_version=stored.content_version,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        created_by=stored.created_by,
        updated_by=stored.updated_by,
    )


class _EventLog:
    """Events of one transaction, with strictly increasing timestamps.

    Several events can share one transaction (auto-deactivation, then
    activation); the history orders on `occurred_at`, so ties are broken here.
    """

    def __init__(self, actor_uid: str) -> None:
        self._actor_uid = actor_uid
        self._last: datetime | None = None
        self.events: list[StoredActivationEvent] = []

    def record(self, stored: StoredAnnouncement, action: str) -> None:
        now = utcnow()
        if self._last is not None and now <= self._last:
            now = self._last + timedelta(microseconds=1)
        self._last = now
        self.events.append(
            StoredActivationEvent(
                id=str(uuid.uuid4()),
                announcement_id=stored.id,
                kind=stored.kind,
                label=dict(stored.title),
                # A patch note's stored severity is a placeholder, not a colour.
                severity=None if stored.kind == "patch_note" else stored.severity,
                action=action,
                actor_uid=self._actor_uid,
                occurred_at=now,
            )
        )


def _content_changed(
    stored: StoredAnnouncement, request: AnnouncementWriteRequest
) -> bool:
    """Whether anything a reader actually sees differs from what is stored.

    `enabled` is excluded here because this path never changes delivery at
    all — see `update_announcement`. `dismissible` IS included: it changes the
    banner's controls.
    """

    return (
        stored.severity != request.severity
        or stored.title != request.title
        or stored.description_short != request.description_short
        or stored.description_long != request.description_long
        or stored.dismissible != request.dismissible
    )


def _versioning_after_edit(stored: StoredAnnouncement, changed: bool) -> int:
    """`content_version` once the content PUT lands.

    A banner bumps on every visible change; a patch note never does here, so a
    typo fix does not re-show it.
    """

    if stored.kind == "patch_note" or not changed:
        return stored.content_version
    return stored.content_version + 1


def _versioning_after_toggle(stored: StoredAnnouncement, enabled: bool) -> int:
    """`content_version` once the toggle lands: every off-to-on bumps it.

    Going back on air is a relaunch, for a banner and a patch note alike.
    """

    if enabled and not stored.enabled:
        return stored.content_version + 1
    return stored.content_version


async def list_announcements(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[AdminAnnouncement]:
    """Every announcement, with each patch note's dismissal count, for the admin page."""

    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    async with store.transaction() as session:
        stored = await store.list_all(session=session)
        counts = await store.count_dismissals(session=session)
    return [
        AdminAnnouncement(
            **_to_announcement(row).model_dump(),
            dismissal_count=counts.get(row.id, 0) if row.kind == "patch_note" else None,
        )
        for row in stored
    ]


async def list_active_announcements(
    *, deps: ProductServiceDependencies
) -> list[Announcement]:
    """The enabled banners, for any authenticated user; patch notes have their own read.

    No authorization check beyond authentication: an announcement is content
    every user of the deployment is meant to see. The route's
    `get_current_user` dependency is what keeps it off the public surface.
    """

    stored = await deps.get_announcement_store().list_enabled()
    return [_to_announcement(row) for row in stored]


async def create_announcement(
    *,
    user: KeycloakUser,
    request: AnnouncementWriteRequest,
    deps: ProductServiceDependencies,
) -> Announcement:
    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    announcement_id = str(uuid.uuid4())
    log = _EventLog(user.uid)
    auto_disabled: list[StoredAnnouncement] = []
    try:
        async with store.transaction() as session:
            if request.enabled and request.kind == "patch_note":
                auto_disabled = await store.disable_other_patch_notes(
                    except_id=announcement_id, updated_by=user.uid, session=session
                )
            stored = await store.create(
                announcement_id=announcement_id,
                kind=request.kind,
                severity=request.severity,
                title=request.title,
                description_short=request.description_short,
                description_long=request.description_long,
                enabled=request.enabled,
                dismissible=request.dismissible,
                created_by=user.uid,
                session=session,
            )
            for previous in auto_disabled:
                log.record(previous, "deactivated")
            if stored.enabled:
                log.record(stored, "activated")
            await store.append_activation_events(log.events, session=session)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_CONCURRENT_ACTIVATION
        ) from exc
    emit_audit_log(
        "platform.announcement.created",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        kind=request.kind,
        severity=request.severity,
        enabled=request.enabled,
        auto_disabled_ids=[previous.id for previous in auto_disabled],
    )
    return _to_announcement(stored)


async def update_announcement(
    *,
    user: KeycloakUser,
    announcement_id: str,
    request: AnnouncementWriteRequest,
    deps: ProductServiceDependencies,
) -> Announcement:
    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    async with store.transaction() as session:
        # Locked: the new content_version is computed from the stored one.
        existing = await store.get(announcement_id, for_update=True, session=session)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
            )
        if existing.kind != request.kind:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="an announcement's kind cannot change",
            )
        content_version = _versioning_after_edit(
            existing, _content_changed(existing, request)
        )
        stored = await store.update(
            announcement_id=announcement_id,
            severity=request.severity,
            title=request.title,
            description_short=request.description_short,
            description_long=request.description_long,
            # Delivery belongs to the `/enabled` route alone: a toggle made
            # while the editor was open stands.
            dismissible=request.dismissible,
            content_version=content_version,
            updated_by=user.uid,
            session=session,
        )
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
            )
    emit_audit_log(
        "platform.announcement.updated",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        severity=request.severity,
        enabled=stored.enabled,
        content_version=content_version,
    )
    return _to_announcement(stored)


async def set_announcement_enabled(
    *,
    user: KeycloakUser,
    announcement_id: str,
    enabled: bool,
    deps: ProductServiceDependencies,
) -> Announcement:
    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    log = _EventLog(user.uid)
    auto_disabled: list[StoredAnnouncement] = []
    try:
        async with store.transaction() as session:
            # Locked so two concurrent toggles cannot both record the change.
            existing = await store.get(
                announcement_id, for_update=True, session=session
            )
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
                )
            changed = existing.enabled != enabled
            if changed and enabled and existing.kind == "patch_note":
                auto_disabled = await store.disable_other_patch_notes(
                    except_id=announcement_id, updated_by=user.uid, session=session
                )
                # A relaunch shows the note to everyone again.
                await store.delete_dismissals(announcement_id, session=session)
            content_version = _versioning_after_toggle(existing, enabled)
            stored = await store.set_enabled(
                announcement_id=announcement_id,
                enabled=enabled,
                content_version=content_version,
                updated_by=user.uid,
                session=session,
            )
            if stored is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
                )
            for previous in auto_disabled:
                log.record(previous, "deactivated")
            if changed:
                log.record(stored, "activated" if enabled else "deactivated")
            await store.append_activation_events(log.events, session=session)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_CONCURRENT_ACTIVATION
        ) from exc
    emit_audit_log(
        "platform.announcement.toggled",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        enabled=enabled,
        content_version=content_version,
        auto_disabled_ids=[previous.id for previous in auto_disabled],
    )
    return _to_announcement(stored)


async def delete_announcement(
    *,
    user: KeycloakUser,
    announcement_id: str,
    deps: ProductServiceDependencies,
) -> None:
    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    log = _EventLog(user.uid)
    async with store.transaction() as session:
        # Locked so two concurrent deletes cannot both record a deactivation.
        existing = await store.get(announcement_id, for_update=True, session=session)
        if existing is None or not await store.delete(announcement_id, session=session):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
            )
        if existing.enabled:
            log.record(existing, "deactivated")
        await store.append_activation_events(log.events, session=session)
    emit_audit_log(
        "platform.announcement.deleted",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        was_enabled=existing.enabled,
    )


async def get_active_patch_note(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> ActivePatchNote:
    """The enabled patch note, flagged when the caller dismissed it.

    Authentication only, like the banner read; identity comes from the token.
    """

    store = deps.get_announcement_store()
    async with store.transaction() as session:
        note = await store.get_enabled_patch_note(session=session)
        if note is None:
            return ActivePatchNote()
        dismissed = await store.is_dismissed(
            announcement_id=note.id, user_id=user.uid, session=session
        )
    return ActivePatchNote(patch_note=_to_announcement(note), dismissed=dismissed)


async def dismiss_patch_note(
    *,
    user: KeycloakUser,
    announcement_id: str,
    deps: ProductServiceDependencies,
) -> None:
    """Record the caller's own "don't show again"; idempotent."""

    store = deps.get_announcement_store()
    stored = await store.get(announcement_id)
    if stored is None or stored.kind != "patch_note":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    try:
        await store.add_dismissal(announcement_id=announcement_id, user_id=user.uid)
    except IntegrityError as exc:
        # The note was deleted between the check above and the insert.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from exc


async def list_activation_history(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[AnnouncementActivationEvent]:
    """The newest activation events, for the admin page."""

    await _require_manage_platform(deps, user)
    events = await deps.get_announcement_store().list_activation_events(
        limit=ACTIVATION_HISTORY_LIMIT
    )
    return [
        AnnouncementActivationEvent(
            id=event.id,
            announcement_id=event.announcement_id,
            kind=event.kind,  # type: ignore[arg-type]
            label=event.label,
            severity=event.severity,  # type: ignore[arg-type]
            action=event.action,  # type: ignore[arg-type]
            actor_uid=event.actor_uid,
            occurred_at=event.occurred_at,
        )
        for event in events
    ]
