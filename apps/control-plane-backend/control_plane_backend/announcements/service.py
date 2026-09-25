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
    AnnouncementWriteRequest,
)
from control_plane_backend.announcements.store import StoredAnnouncement
from control_plane_backend.product.dependencies import ProductServiceDependencies


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


def _content_changed(
    stored: StoredAnnouncement, request: AnnouncementWriteRequest
) -> bool:
    """Whether anything a reader actually sees differs from what is stored.

    `enabled` is excluded here because it says nothing about the wording; the
    transition that matters is handled by `_relaunched`. `dismissible` IS
    included — it changes the banner's controls.
    """

    return (
        stored.severity != request.severity
        or stored.title != request.title
        or stored.description_short != request.description_short
        or stored.description_long != request.description_long
        or stored.dismissible != request.dismissible
    )


def _relaunched(stored: StoredAnnouncement, enabled: bool) -> bool:
    """Whether a disabled announcement is going back on air.

    A relaunch must reach the users who closed the previous run. Their
    dismissals live in their own browser's storage, keyed by content version,
    so bumping that version is the only lever the server has. Turning an
    announcement off never bumps, and neither does re-sending `enabled=True`
    on one that is already live.
    """

    return enabled and not stored.enabled


async def list_announcements(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> list[Announcement]:
    """Every announcement, for the admin page."""

    await _require_manage_platform(deps, user)
    stored = await deps.get_announcement_store().list_all()
    return [_to_announcement(row) for row in stored]


async def list_active_announcements(
    *, deps: ProductServiceDependencies
) -> list[Announcement]:
    """The enabled announcements, for any authenticated user.

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
    announcement_id = str(uuid.uuid4())
    stored = await deps.get_announcement_store().create(
        announcement_id=announcement_id,
        severity=request.severity,
        title=request.title,
        description_short=request.description_short,
        description_long=request.description_long,
        enabled=request.enabled,
        dismissible=request.dismissible,
        created_by=user.uid,
    )
    emit_audit_log(
        "platform.announcement.created",
        actor_uid=user.uid,
        announcement_id=announcement_id,
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
    existing = await store.get(announcement_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="announcement not found"
        )

    bumped = _content_changed(existing, request) or _relaunched(
        existing, request.enabled
    )
    content_version = existing.content_version + (1 if bumped else 0)
    stored = await store.update(
        announcement_id=announcement_id,
        severity=request.severity,
        title=request.title,
        description_short=request.description_short,
        description_long=request.description_long,
        enabled=request.enabled,
        dismissible=request.dismissible,
        content_version=content_version,
        updated_by=user.uid,
    )
    if stored is None:
        # Deleted between the read and the write.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="announcement not found"
        )
    emit_audit_log(
        "platform.announcement.updated",
        actor_uid=user.uid,
        announcement_id=announcement_id,
        severity=request.severity,
        enabled=request.enabled,
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
    existing = await store.get(announcement_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="announcement not found"
        )

    content_version = existing.content_version + (
        1 if _relaunched(existing, enabled) else 0
    )
    stored = await store.set_enabled(
        announcement_id=announcement_id,
        enabled=enabled,
        content_version=content_version,
        updated_by=user.uid,
    )
    if stored is None:
        # Deleted between the read and the write.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="announcement not found"
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
    deleted = await deps.get_announcement_store().delete(announcement_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="announcement not found"
        )
    emit_audit_log(
        "platform.announcement.deleted",
        actor_uid=user.uid,
        announcement_id=announcement_id,
    )
