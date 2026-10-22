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

"""The caller's own notifications, and the platform admin's switch per type.
No route creates one: the control-plane services that emit them compute their
recipients."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.notifications.schemas import (
    MAX_PAGE_SIZE,
    MarkNotificationsSeenRequest,
    NotificationPage,
    NotificationSummary,
    NotificationType,
    NotificationTypeSetting,
    NotificationTypeSettings,
    SetNotificationTypeRequest,
)
from control_plane_backend.notifications.service import (
    InvalidNotificationCursor,
    NotificationNotFound,
    NotificationService,
)

router = APIRouter(tags=["Notifications"])

_NOT_FOUND = "notification not found"


def get_notification_service(request: Request) -> NotificationService:
    return get_application_container(request).get_notification_service()


Notifications = Annotated[NotificationService, Depends(get_notification_service)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.get(
    "/notifications/summary",
    response_model=NotificationSummary,
    summary="Count the caller's unseen notifications.",
)
async def get_notification_summary(
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> NotificationSummary:
    """Polled by the badge while the tab is visible: one indexed count."""
    return await notifications.summary(user)


@router.get(
    "/notifications",
    response_model=NotificationPage,
    summary="List the caller's notifications, newest first.",
)
async def list_notifications(
    notifications: Notifications,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    before: Annotated[
        str | None, Query(description="`next_cursor` of the previous page.")
    ] = None,
    user: KeycloakUser = Depends(get_current_user),
) -> NotificationPage:
    try:
        return await notifications.list_page(user, limit=limit, before=before)
    except InvalidNotificationCursor as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post(
    "/notifications/seen",
    response_model=NotificationSummary,
    summary="Mark the caller's notifications seen up to the newest one listed.",
)
async def mark_notifications_seen(
    request: MarkNotificationsSeenRequest,
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> NotificationSummary:
    """A notification created after `up_to` stays unseen. Answers `404` when
    `up_to` is not one of the caller's notifications."""
    try:
        return await notifications.mark_seen(user, request.up_to)
    except NotificationNotFound as exc:
        raise _not_found() from exc


@router.delete(
    "/notifications/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the caller's notifications.",
)
async def delete_notification(
    notification_id: str,
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    try:
        await notifications.delete(user, notification_id)
    except NotificationNotFound as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/notifications",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the caller's notifications, except decisions still waiting.",
)
async def clear_notifications(
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    await notifications.clear(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/platform/notification-types",
    response_model=NotificationTypeSettings,
    summary="List every notification type and whether it is sent (platform admin).",
)
async def list_notification_types(
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> NotificationTypeSettings:
    return await notifications.list_type_settings(user)


@router.put(
    "/admin/platform/notification-types/{notification_type}",
    response_model=NotificationTypeSetting,
    summary="Turn one notification type on or off for the platform (platform admin).",
)
async def set_notification_type(
    notification_type: NotificationType,
    request: SetNotificationTypeRequest,
    notifications: Notifications,
    user: KeycloakUser = Depends(get_current_user),
) -> NotificationTypeSetting:
    """Off hides every notification of the type from everyone until it is on again."""
    return await notifications.set_type_enabled(
        user, notification_type, request.enabled
    )
