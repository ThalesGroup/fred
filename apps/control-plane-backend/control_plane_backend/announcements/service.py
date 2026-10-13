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

from fastapi import HTTPException, status
from fred_core import KeycloakUser, OrganizationPermission
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

from control_plane_backend.announcements.schemas import (
    Announcement,
    AnnouncementExposure,
    AnnouncementWriteRequest,
    PatchNoteAnnouncement,
    PatchNoteHistory,
    PatchNoteSnapshot,
)
from control_plane_backend.announcements.store import (
    StoredAnnouncement,
    StoredExposure,
)
from control_plane_backend.models.announcement_models import (
    MAX_PATCH_NOTES_PER_ANNOUNCEMENT,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.product.dependencies import ProductServiceDependencies

#: How many exposure lines the admin history returns (no pagination).
EXPOSURE_HISTORY_LIMIT = 100

_NOT_FOUND = "announcement not found"
_STALE_ORDER = "the patch notes changed meanwhile; reload and retry"
_NOTHING_INCLUDED = "no patch note is included; nothing to announce"
_TOO_MANY_INCLUDED = (
    f"an announcement holds at most {MAX_PATCH_NOTES_PER_ANNOUNCEMENT} patch "
    "notes; leave some out and retry"
)
_SELECTION_CHANGED = (
    "the included patch notes changed since the confirmation; reload and retry"
)
_NO_ANNOUNCEMENT = "no announcement is in effect"


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


def _to_patch_note_announcement(exposure: StoredExposure) -> PatchNoteAnnouncement:
    return PatchNoteAnnouncement(
        id=exposure.id,
        announced_at=exposure.activated_at,
        announced_by=exposure.actor_uid,
    )


def _to_snapshots(exposure: StoredExposure) -> list[PatchNoteSnapshot]:
    return [PatchNoteSnapshot(**note) for note in exposure.package or []]


def _banner_exposure(stored: StoredAnnouncement, actor_uid: str) -> StoredExposure:
    """The history line a banner starts when it goes on air."""

    return StoredExposure(
        id=str(uuid.uuid4()),
        kind=stored.kind,
        announcement_id=stored.id,
        label=dict(stored.title),
        severity=stored.severity,
        actor_uid=actor_uid,
        activated_at=utcnow(),
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
        # Only a banner is on air once enabled; a patch note waits to be announced.
        if stored.enabled and stored.kind == "banner":
            await store.add_exposure(
                _banner_exposure(stored, user.uid), session=session
            )
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
        if changed and stored.kind == "banner":
            if enabled:
                await store.add_exposure(
                    _banner_exposure(stored, user.uid), session=session
                )
            else:
                await store.end_exposures(
                    kind="banner",
                    announcement_id=stored.id,
                    at=utcnow(),
                    session=session,
                )
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
    async with store.transaction() as session:
        # Locked so two concurrent deletes cannot both end the exposure.
        existing = await store.get(announcement_id, for_update=True, session=session)
        if existing is None or not await store.delete(announcement_id, session=session):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
            )
        if existing.enabled and existing.kind == "banner":
            await store.end_exposures(
                kind="banner",
                announcement_id=existing.id,
                at=utcnow(),
                session=session,
            )
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
    *,
    user: KeycloakUser,
    expected_ids: list[str],
    deps: ProductServiceDependencies,
) -> PatchNoteAnnouncement:
    """Freeze the included patch notes as a package: every user gets the dialog once.

    Refused unless they are exactly `expected_ids`, in order: what the
    administrator confirmed is what gets frozen.
    """

    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    async with store.transaction() as session:
        # One announce or withdraw at a time: never two announcements in effect.
        await store.lock_patch_notes(session=session)
        included = await store.list_included_patch_notes(session=session)
        if not included:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_NOTHING_INCLUDED
            )
        if len(included) > MAX_PATCH_NOTES_PER_ANNOUNCEMENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_TOO_MANY_INCLUDED
            )
        if [note.id for note in included] != expected_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_SELECTION_CHANGED
            )
        now = utcnow()
        exposure = StoredExposure(
            id=str(uuid.uuid4()),
            kind="patch_note",
            announcement_id=included[0].id,
            label=dict(included[0].title),
            actor_uid=user.uid,
            activated_at=now,
            note_count=len(included),
            package=[
                {
                    "id": note.id,
                    "title": note.title,
                    "description_long": note.description_long,
                }
                for note in included
            ],
        )
        # The new package replaces the one in effect, at the same instant.
        await store.end_exposures(kind="patch_note", at=now, session=session)
        await store.add_exposure(exposure, session=session)
    emit_audit_log(
        "platform.announcement.patch_notes_announced",
        actor_uid=user.uid,
        announcement_id=exposure.id,
        patch_note_ids=[note.id for note in included],
    )
    return _to_patch_note_announcement(exposure)


async def withdraw_patch_note_announcement(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> None:
    """End the announcement in effect: users read nothing until the next one."""

    await _require_manage_platform(deps, user)
    store = deps.get_announcement_store()
    async with store.transaction() as session:
        await store.lock_patch_notes(session=session)
        current = await store.get_announcement_in_effect(session=session)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_NO_ANNOUNCEMENT
            )
        await store.end_exposures(kind="patch_note", at=utcnow(), session=session)
    emit_audit_log(
        "platform.announcement.patch_notes_withdrawn",
        actor_uid=user.uid,
        announcement_id=current.id,
    )


async def get_patch_note_announcement(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PatchNoteAnnouncement | None:
    """The announcement in effect, or `None` when none was made or it was withdrawn."""

    await _require_manage_platform(deps, user)
    current = await deps.get_announcement_store().get_announcement_in_effect()
    return None if current is None else _to_patch_note_announcement(current)


async def get_patch_note_package(
    *, user: KeycloakUser, announcement_id: str, deps: ProductServiceDependencies
) -> list[PatchNoteSnapshot]:
    """The package of one history line, as users saw it."""

    await _require_manage_platform(deps, user)
    exposure = await deps.get_announcement_store().get_exposure(
        announcement_id, with_package=True
    )
    # An older patch-note line kept no package: nothing to open.
    if exposure is None or exposure.note_count is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return _to_snapshots(exposure)


async def get_patch_note_history(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PatchNoteHistory:
    """The package in effect, and whether the caller has still to see it.

    Authentication only, like the banner read; identity comes from the token.
    """

    store = deps.get_announcement_store()
    async with store.transaction() as session:
        current = await store.get_announcement_in_effect(
            with_package=True, session=session
        )
        if current is None:
            return PatchNoteHistory(patch_notes=[])
        pending = None
        if current.opens_dialog:
            seen = await store.get_seen_announcement_id(user.uid, session=session)
            pending = None if seen == current.id else current.id
    return PatchNoteHistory(
        patch_notes=_to_snapshots(current), pending_announcement_id=pending
    )


async def mark_patch_note_announcement_seen(
    *,
    user: KeycloakUser,
    announcement_id: str,
    deps: ProductServiceDependencies,
) -> None:
    """Record that the caller saw that announcement; idempotent."""

    store = deps.get_announcement_store()
    exposure = await store.get_exposure(announcement_id)
    if exposure is None or exposure.note_count is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    seen_id = await store.get_seen_announcement_id(user.uid)
    if seen_id == exposure.id:
        return
    if seen_id is not None:
        seen = await store.get_exposure(seen_id)
        # A late close of an older dialog must not undo a newer record.
        if seen is not None and seen.activated_at > exposure.activated_at:
            return
    await store.set_seen_announcement(user_id=user.uid, announcement_id=exposure.id)


async def list_exposure_history(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[AnnouncementExposure]:
    """The newest history lines, for the admin page."""

    await _require_manage_platform(deps, user)
    exposures = await deps.get_announcement_store().list_exposures(
        limit=EXPOSURE_HISTORY_LIMIT
    )
    return [
        AnnouncementExposure(
            id=exposure.id,
            kind=exposure.kind,  # type: ignore[arg-type]
            announcement_id=exposure.announcement_id,
            label=exposure.label,
            severity=exposure.severity,  # type: ignore[arg-type]
            note_count=exposure.note_count,
            activated_at=exposure.activated_at,
            deactivated_at=exposure.deactivated_at,
            actor_uid=exposure.actor_uid,
        )
        for exposure in exposures
    ]
