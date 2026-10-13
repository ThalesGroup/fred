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

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.announcements import service
from control_plane_backend.announcements.schemas import (
    Announcement,
    AnnouncementExposure,
    AnnouncementWriteRequest,
    PatchNoteAnnouncement,
    PatchNoteHistory,
    PatchNoteOrderRequest,
    PatchNoteSnapshot,
    SetAnnouncementEnabledRequest,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["Announcements"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.get(
    "/announcements/active",
    response_model=list[Announcement],
    summary="List the banners currently delivered to users.",
)
async def get_active_announcements(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[Announcement]:
    """Every authenticated user's view: the enabled banners (never patch notes).

    Authentication is the only gate — this is content the deployment means
    every user to see. It is deliberately NOT on the public pre-auth
    `/frontend/config` surface the retired deploy-time banner used: these rows
    are admin-authored at runtime and must not be readable by an
    unauthenticated visitor.
    """

    del user  # authentication is the gate; identity is not used
    return await service.list_active_announcements(deps=deps)


@router.get(
    "/announcements/patch-notes",
    response_model=PatchNoteHistory,
    summary="List the announced patch notes and the caller's pending announcement.",
)
async def get_patch_note_history(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PatchNoteHistory:
    """Read once per application load. A non-null `pending_announcement_id`
    tells the client to open the dialog on its own, then record that id."""

    return await service.get_patch_note_history(user=user, deps=deps)


@router.put(
    "/announcements/patch-note-announcements/{announcement_id}/seen",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record that the caller saw a patch-note announcement.",
)
async def mark_patch_note_announcement_seen(
    announcement_id: str,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    await service.mark_patch_note_announcement_seen(
        user=user, announcement_id=announcement_id, deps=deps
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/admin/platform/announcements/patch-notes/order",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set the order of the patch notes (admin).",
)
async def set_patch_note_order(
    request: PatchNoteOrderRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """Answers `409` when the list is not exactly the current patch notes."""

    await service.set_patch_note_order(user=user, ordered_ids=request.ids, deps=deps)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/platform/announcements/patch-notes/announcement",
    response_model=PatchNoteAnnouncement | None,
    summary="Get the patch-note announcement in effect, if any (admin).",
)
async def get_patch_note_announcement(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PatchNoteAnnouncement | None:
    return await service.get_patch_note_announcement(user=user, deps=deps)


@router.post(
    "/admin/platform/announcements/patch-notes/announcement",
    response_model=PatchNoteAnnouncement,
    status_code=status.HTTP_201_CREATED,
    summary="Announce the included patch notes to every user (admin).",
)
async def announce_patch_notes(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PatchNoteAnnouncement:
    """Freezes the included patch notes as the package users read. Answers
    `409` when no patch note is included."""

    return await service.announce_patch_notes(user=user, deps=deps)


@router.delete(
    "/admin/platform/announcements/patch-notes/announcement",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw the patch-note announcement in effect (admin).",
)
async def withdraw_patch_note_announcement(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """Users read no patch note until the next announcement. Answers `404`
    when no announcement is in effect."""

    await service.withdraw_patch_note_announcement(user=user, deps=deps)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/platform/announcements/patch-notes/announcements/{announcement_id}",
    response_model=list[PatchNoteSnapshot],
    summary="Get the patch notes of one announcement, as users saw them (admin).",
)
async def get_patch_note_package(
    announcement_id: str,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[PatchNoteSnapshot]:
    """Answers `404` for a history line that kept no package."""

    return await service.get_patch_note_package(
        user=user, announcement_id=announcement_id, deps=deps
    )


@router.get(
    "/admin/platform/announcements/activation-history",
    response_model=list[AnnouncementExposure],
    summary="List the latest banner and patch-note exposures (admin).",
)
async def list_exposure_history(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[AnnouncementExposure]:
    return await service.list_exposure_history(user=user, deps=deps)


@router.get(
    "/admin/platform/announcements",
    response_model=list[Announcement],
    summary="List every announcement (admin).",
)
async def list_announcements(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[Announcement]:
    return await service.list_announcements(user=user, deps=deps)


@router.post(
    "/admin/platform/announcements",
    response_model=Announcement,
    status_code=status.HTTP_201_CREATED,
    summary="Create an announcement (admin).",
)
async def create_announcement(
    request: AnnouncementWriteRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Announcement:
    return await service.create_announcement(user=user, request=request, deps=deps)


@router.put(
    "/admin/platform/announcements/{announcement_id}",
    response_model=Announcement,
    summary="Replace an announcement's content (admin).",
)
async def update_announcement(
    announcement_id: str,
    request: AnnouncementWriteRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Announcement:
    return await service.update_announcement(
        user=user, announcement_id=announcement_id, request=request, deps=deps
    )


@router.put(
    "/admin/platform/announcements/{announcement_id}/enabled",
    response_model=Announcement,
    summary="Enable or disable an announcement (admin).",
)
async def set_announcement_enabled(
    announcement_id: str,
    request: SetAnnouncementEnabledRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Announcement:
    """Re-enabling a banner bumps `content_version`. On a patch note this only
    decides whether the next announcement includes it."""

    return await service.set_announcement_enabled(
        user=user,
        announcement_id=announcement_id,
        enabled=request.enabled,
        deps=deps,
    )


@router.delete(
    "/admin/platform/announcements/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an announcement (admin).",
)
async def delete_announcement(
    announcement_id: str,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    await service.delete_announcement(
        user=user, announcement_id=announcement_id, deps=deps
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
