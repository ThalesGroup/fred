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
    AnnouncementWriteRequest,
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
    summary="List the announcements currently delivered to users.",
)
async def get_active_announcements(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[Announcement]:
    """Every authenticated user's view: the enabled announcements.

    Authentication is the only gate — this is content the deployment means
    every user to see. It is deliberately NOT on the public pre-auth
    `/frontend/config` surface the retired deploy-time banner used: these rows
    are admin-authored at runtime and must not be readable by an
    unauthenticated visitor.
    """

    del user  # authentication is the gate; identity is not used
    return await service.list_active_announcements(deps=deps)


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
    """Separate from the content update so a toggle never bumps
    `content_version` — a dismissed banner must not come back because an admin
    flicked the switch."""

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
