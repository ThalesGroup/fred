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
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.announcements.schemas import (
    Announcement,
    AnnouncementActivationEvent,
    AnnouncementWriteRequest,
    PatchNoteAnnouncement,
    PatchNoteHistory,
)
from control_plane_backend.announcements.store import (
    AnnouncementStore,
    StoredActivationEvent,
    StoredAnnouncement,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.product.dependencies import ProductServiceDependencies

#: How many activation events the admin history returns (no pagination).
ACTIVATION_HISTORY_LIMIT = 100

_NOT_FOUND = "announcement not found"
_STALE_ORDER = "the patch notes changed meanwhile; reload and retry"
_NOTHING_VISIBLE = "no patch note is visible; nothing to announce"


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
        position=stored.position,
    )


def _to_patch_note_announcement(event: StoredActivationEvent) -> PatchNoteAnnouncement:
    return PatchNoteAnnouncement(
        id=event.id, announced_at=event.occurred_at, announced_by=event.actor_uid
    )


class _EventLog:
    """Events of one transaction, with strictly increasing timestamps.

    Several events can share one transaction (deactivation, then the
    cancelled announcement); the history orders on `occurred_at`, so ties are
    broken here.
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

    A banner bumps on every visible change; a patch note never does, since
    nothing is keyed on it.
    """

    if stored.kind == "patch_note" or not changed:
        return stored.content_version
    return stored.content_version + 1


def _versioning_after_toggle(stored: StoredAnnouncement, enabled: bool) -> int:
    """`content_version` once the toggle lands: every off-to-on bumps it.

    Going back on air relaunches a banner; nothing reads it on a patch note.
    """

    if enabled and not stored.enabled:
        return stored.content_version + 1
    return stored.content_version


async def _cancel_announcement_if_nothing_visible(
    store: AnnouncementStore,
    hidden: StoredAnnouncement,
    log: _EventLog,
    session: AsyncSession,
) -> None:
    """Record `unannounced` when `hidden` was the last visible patch note.

    Otherwise the announcement would fire later, on notes nobody announced.
    """

    if hidden.kind != "patch_note":
        return
    if await store.list_visible_patch_notes(session=session):
        return
    if await store.get_current_announcement(session=session) is not None:
        log.record(hidden, "unannounced")


async def list_announcements(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[Announcement]:
    """Every announcement for the admin page: banners, then patch notes in order."""

    await _require_manage_platform(deps, user)
    stored = await deps.get_announcement_store().list_all()
    return [_to_announcement(row) for row in stored]


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
    async with store.transaction() as session:
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
        if stored.enabled:
            log.record(stored, "activated")
        await store.append_activation_events(log.events, session=session)
    emit_audit_log(
        "platform.announcement.created",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        kind=request.kind,
        severity=request.severity,
        enabled=request.enabled,
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
    async with store.transaction() as session:
        # Locked so two concurrent toggles cannot both record the change.
        existing = await store.get(announcement_id, for_update=True, session=session)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
            )
        changed = existing.enabled != enabled
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
        if changed:
            log.record(stored, "activated" if enabled else "deactivated")
            if not enabled:
                await _cancel_announcement_if_nothing_visible(
                    store, stored, log, session
                )
        await store.append_activation_events(log.events, session=session)
    emit_audit_log(
        "platform.announcement.toggled",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        enabled=enabled,
        content_version=content_version,
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
            await _cancel_announcement_if_nothing_visible(store, existing, log, session)
        await store.append_activation_events(log.events, session=session)
    emit_audit_log(
        "platform.announcement.deleted",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        was_enabled=existing.enabled,
    )


async def set_patch_note_order(
    *,
    user: KeycloakUser,
    ordered_ids: list[str],
    deps: ProductServiceDependencies,
) -> None:
    """Store the administrator's order; refuses a list that is not the current set."""

    await _require_manage_platform(deps, user)
    if not await deps.get_announcement_store().set_patch_note_order(ordered_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_STALE_ORDER)
    emit_audit_log(
        "platform.announcement.patch_notes_reordered",
        actor_uid=user.uid,
        ordered_ids=ordered_ids,
    )


async def announce_patch_notes(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PatchNoteAnnouncement:
    """Announce the visible patch notes: every user gets the dialog once."""

    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    log = _EventLog(user.uid)
    async with store.transaction() as session:
        visible = await store.list_visible_patch_notes(session=session)
        if not visible:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_NOTHING_VISIBLE
            )
        # Snapshots the note users will open on.
        log.record(visible[0], "announced")
        await store.append_activation_events(log.events, session=session)
    event = log.events[0]
    emit_audit_log(
        "platform.announcement.patch_notes_announced",
        actor_uid=user.uid,
        announcement_event_id=event.id,
        first_patch_note_id=event.announcement_id,
        visible_count=len(visible),
    )
    return _to_patch_note_announcement(event)


async def get_patch_note_announcement(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PatchNoteAnnouncement | None:
    """The announcement in effect, or `None` when none was made or it was cancelled."""

    await _require_manage_platform(deps, user)
    event = await deps.get_announcement_store().get_current_announcement()
    return None if event is None else _to_patch_note_announcement(event)


async def get_patch_note_history(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PatchNoteHistory:
    """The visible patch notes, and the announcement the caller has not seen.

    Authentication only, like the banner read; identity comes from the token.
    """

    store = deps.get_announcement_store()
    async with store.transaction() as session:
        notes = await store.list_visible_patch_notes(session=session)
        current = await store.get_current_announcement(session=session)
        pending = None
        # `notes` is checked too: two concurrent toggles can hide everything
        # without either cancelling the announcement.
        if notes and current is not None:
            seen = await store.get_seen_announcement_id(user.uid, session=session)
            pending = None if seen == current.id else current.id
    return PatchNoteHistory(
        patch_notes=[_to_announcement(note) for note in notes],
        pending_announcement_id=pending,
    )


async def mark_patch_note_announcement_seen(
    *,
    user: KeycloakUser,
    announcement_event_id: str,
    deps: ProductServiceDependencies,
) -> None:
    """Record that the caller saw that announcement; idempotent."""

    store = deps.get_announcement_store()
    event = await store.get_activation_event(announcement_event_id)
    if event is None or event.action != "announced":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    seen_id = await store.get_seen_announcement_id(user.uid)
    if seen_id == event.id:
        return
    if seen_id is not None:
        seen = await store.get_activation_event(seen_id)
        # A late close of an older dialog must not undo a newer record.
        if seen is not None and seen.occurred_at > event.occurred_at:
            return
    await store.set_seen_announcement(user_id=user.uid, announcement_event_id=event.id)


async def list_activation_history(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[AnnouncementActivationEvent]:
    """The newest history events, for the admin page."""

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
