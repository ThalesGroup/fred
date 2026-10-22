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

"""Requests to join an `on_request` team: a non-member asks, the team admins
accept or refuse through a notification or the Members tab.

Notifications are sent after each write and are best effort. Full rules:
`openspec/changes/add-team-join-requests/design.md`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from fred_core import (
    JoiningMode,
    KeycloakUser,
    RelationType,
    TeamPermission,
    TeamVisibility,
)
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.teams.metadata_store import TeamMetadata

from control_plane_backend.models.base import utcnow
from control_plane_backend.notifications.schemas import (
    TeamJoinRequestAnsweredPayload,
    TeamJoinRequestedPayload,
)
from control_plane_backend.notifications.service import (
    NotificationService,
    display_name,
)
from control_plane_backend.notifications.store import NotificationDraft
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.join_request_store import (
    JoinRequestStatus,
    StoredJoinRequest,
    answer_group,
    request_group,
)
from control_plane_backend.teams.schemas import (
    MyTeamJoinRequest,
    TeamJoinRequest,
    TeamJoinRequestError,
    TeamNotFoundError,
    UserTeamRelation,
)
from control_plane_backend.teams.service import (
    _add_team_member_relation,
    _get_team_users_by_relation,
    _get_user_roles_in_team,
    _on_team_access_changed,
    _validate_team_and_check_permission,
)

logger = logging.getLogger(__name__)


def _lock_key(team_id: TeamId) -> str:
    # Serializes asking with the sweep of a team that stops taking requests.
    return f"team_join_requests:{team_id}"


def _takes_requests(metadata: TeamMetadata) -> bool:
    return (
        metadata.visibility == TeamVisibility.PUBLIC
        and metadata.joining_mode == JoiningMode.ON_REQUEST
    )


def _mine_view(request: StoredJoinRequest) -> MyTeamJoinRequest:
    return MyTeamJoinRequest(
        id=request.id,
        team_id=request.team_id,
        status=request.status.value,
        created_at=request.created_at,
        decided_at=request.decided_at,
        can_ask_again_at=request.can_ask_again_at,
    )


def _team_view(request: StoredJoinRequest) -> TeamJoinRequest:
    return TeamJoinRequest(
        id=request.id,
        team_id=request.team_id,
        requester_id=request.requester_id,
        requester_name=request.requester_name,
        message=request.message,
        status=request.status.value,
        created_at=request.created_at,
        decided_at=request.decided_at,
        expires_at=request.expires_at,
    )


def _audit(
    event: str, actor: KeycloakUser, request: StoredJoinRequest, **extra: object
) -> None:
    # Ids only: the request message never reaches logs.
    emit_audit_log(
        f"team.join_request.{event}",
        actor_uid=actor.uid,
        team_id=request.team_id,
        request_id=request.id,
        **extra,
    )


async def _require_admin(
    user: KeycloakUser, team_id: TeamId, deps: TeamServiceDependencies
) -> TeamMetadata:
    metadata, _ = await _validate_team_and_check_permission(
        user, team_id, deps.rebac, [TeamPermission.CAN_ADMINISTER_MEMBERS], deps
    )
    return metadata


async def create_join_request(
    user: KeycloakUser,
    team_id: TeamId,
    message: str | None,
    deps: TeamServiceDependencies,
) -> tuple[MyTeamJoinRequest, bool]:
    """The caller's pending request to the team; `True` when it is new."""
    teams = deps.get_team_metadata_store()
    # Under the lock the team either still takes requests once the admins are
    # told, or its sweep runs after and finds this request.
    async with teams.advisory_lock(_lock_key(team_id)):
        metadata = await teams.get_by_team_id(team_id)
        # A private team is invisible to a non-member: same answer as no team.
        if metadata is None or metadata.visibility != TeamVisibility.PUBLIC:
            raise TeamNotFoundError(team_id)
        if metadata.joining_mode != JoiningMode.ON_REQUEST:
            raise TeamJoinRequestError.not_on_request()
        if await _get_user_roles_in_team(deps.rebac, team_id, user.uid):
            raise TeamJoinRequestError.already_member()
        created = await _create(user, team_id, message, deps)
        if isinstance(created, MyTeamJoinRequest):
            return created, False
        _audit("created", user, created)
        await _notify_admins(metadata, created, deps)
    return _mine_view(created), True


async def _create(
    user: KeycloakUser,
    team_id: TeamId,
    message: str | None,
    deps: TeamServiceDependencies,
) -> StoredJoinRequest | MyTeamJoinRequest:
    """The new request, or the caller's pending one already there."""
    store = deps.get_team_join_request_store()
    existing = await store.get_mine(team_id, user.uid)
    if existing is not None and existing.status == JoinRequestStatus.PENDING:
        return _mine_view(existing)
    ask_again_at = existing.can_ask_again_at if existing is not None else None
    if ask_again_at is not None and ask_again_at > utcnow():
        raise TeamJoinRequestError.refused()
    created = await store.create(
        team_id=team_id,
        requester_id=user.uid,
        requester_name=display_name(user),
        message=message,
    )
    if created is not None:
        return created
    # Another call of the same person won the slot.
    existing = await store.get_mine(team_id, user.uid)
    if existing is not None and existing.status == JoinRequestStatus.PENDING:
        return _mine_view(existing)
    raise TeamJoinRequestError.refused()


async def _notify_admins(
    metadata: TeamMetadata, request: StoredJoinRequest, deps: TeamServiceDependencies
) -> None:
    try:
        admins = await _get_team_users_by_relation(
            deps.rebac, metadata.id, RelationType.TEAM_ADMIN
        )
    except Exception:
        logger.warning("Failed to list admins team_id=%s", metadata.id, exc_info=True)
        return
    payload = TeamJoinRequestedPayload(
        team_id=metadata.id,
        team_name=metadata.name,
        request_id=request.id,
        requester_id=request.requester_id,
        requester_name=request.requester_name,
        message=request.message,
    )
    # notify() keeps only the admins holding can_administer_members.
    await deps.get_notification_service().notify(
        [
            NotificationDraft(
                recipient_id=admin,
                group_key=request_group(request.id),
                team_id=metadata.id,
                payload=payload,
            )
            for admin in sorted(admins)
        ]
    )


async def cancel_my_join_request(
    user: KeycloakUser, team_id: TeamId, deps: TeamServiceDependencies
) -> None:
    cancelled = await deps.get_team_join_request_store().delete_pending_mine(
        team_id, user.uid
    )
    if cancelled is None:
        raise TeamJoinRequestError.not_found()
    _audit("cancelled", user, cancelled)
    await deps.get_notification_service().delete_groups([request_group(cancelled.id)])


async def list_my_join_requests(
    user: KeycloakUser, deps: TeamServiceDependencies
) -> list[MyTeamJoinRequest]:
    requests = await deps.get_team_join_request_store().list_for_requester(user.uid)
    return [_mine_view(r) for r in requests]


async def list_team_join_requests(
    user: KeycloakUser, team_id: TeamId, deps: TeamServiceDependencies
) -> list[TeamJoinRequest]:
    await _require_admin(user, team_id, deps)
    requests = await deps.get_team_join_request_store().list_for_team(team_id)
    return [_team_view(r) for r in requests]


async def accept_join_request(
    user: KeycloakUser,
    team_id: TeamId,
    request_id: str,
    deps: TeamServiceDependencies,
) -> None:
    """Accept a pending request, or a refused one ("Accept anyway") while the
    team still takes requests."""
    metadata = await _require_admin(user, team_id, deps)
    store = deps.get_team_join_request_store()
    request = await store.get(team_id, request_id)
    if request is None:
        raise TeamJoinRequestError.not_found()
    if not _takes_requests(metadata):
        raise TeamJoinRequestError.not_on_request()
    if await _joined_meanwhile(request, deps):
        return
    # Membership first: if the grant fails the request is still there to decide.
    await _add_team_member_relation(
        deps.rebac, team_id, request.requester_id, UserTeamRelation.TEAM_MEMBER
    )
    if not await store.delete(request.id):
        return  # another admin accepted it first and tells everyone
    _audit("accepted", user, request, requester_uid=request.requester_id)

    notifications = deps.get_notification_service()
    await notifications.resolve(
        [request_group(request.id)],
        actor_uid=user.uid,
        actor_name=display_name(user),
        outcome="accepted",
        # Tiles already reading "refused" show the final outcome.
        include_handled=True,
    )
    # The acceptance replaces any refusal the requester already got.
    await notifications.delete_groups([answer_group(request.id)])
    await _answer(notifications, metadata, [request], "accepted")


async def _joined_meanwhile(
    request: StoredJoinRequest, deps: TeamServiceDependencies
) -> bool:
    """A requester who became a member another way gets no answer."""
    if not await _get_user_roles_in_team(
        deps.rebac, TeamId(request.team_id), request.requester_id
    ):
        return False
    await _on_team_access_changed(deps, TeamId(request.team_id), request.requester_id)
    return True


async def refuse_join_request(
    user: KeycloakUser,
    team_id: TeamId,
    request_id: str,
    deps: TeamServiceDependencies,
) -> None:
    metadata = await _require_admin(user, team_id, deps)
    store = deps.get_team_join_request_store()
    request = await store.get(team_id, request_id)
    if request is None:
        raise TeamJoinRequestError.not_found()
    if request.status == JoinRequestStatus.REFUSED:
        return
    if await _joined_meanwhile(request, deps):
        return
    refused = await store.refuse(team_id, [request_id], decided_by=user.uid)
    if not refused:
        raise TeamJoinRequestError.not_found()
    await _announce_refusals(user, metadata, refused, deps)


async def refuse_pending_join_requests(
    user: KeycloakUser, metadata: TeamMetadata, deps: TeamServiceDependencies
) -> None:
    """The team stopped taking requests: the pending ones are answered "refused"
    but deleted, so this refusal never makes anyone wait to ask again."""
    store = deps.get_team_join_request_store()
    async with deps.get_team_metadata_store().advisory_lock(_lock_key(metadata.id)):
        refused = await store.delete_pending_for_team(metadata.id)
    await _announce_refusals(
        user, metadata, refused, deps, reason="joining_mode_changed"
    )


async def _announce_refusals(
    user: KeycloakUser,
    metadata: TeamMetadata,
    refused: Sequence[StoredJoinRequest],
    deps: TeamServiceDependencies,
    *,
    reason: str | None = None,
) -> None:
    for request in refused:
        _audit(
            "refused", user, request, requester_uid=request.requester_id, reason=reason
        )
    if not refused:
        return
    notifications = deps.get_notification_service()
    await notifications.resolve(
        [request_group(r.id) for r in refused],
        actor_uid=user.uid,
        actor_name=display_name(user),
        outcome="refused",
    )
    await _answer(notifications, metadata, refused, "refused")


async def _answer(
    notifications: NotificationService,
    metadata: TeamMetadata,
    requests: Sequence[StoredJoinRequest],
    outcome: Literal["accepted", "refused"],
) -> None:
    payload = TeamJoinRequestAnsweredPayload(
        team_id=metadata.id, team_name=metadata.name, outcome=outcome
    )
    # An acceptance carries the team so leaving it, or its deletion, takes the
    # "Open the team" tile along; a refusal has no team action and stays.
    await notifications.notify(
        [
            NotificationDraft(
                recipient_id=r.requester_id,
                group_key=answer_group(r.id),
                payload=payload,
                team_id=metadata.id if outcome == "accepted" else None,
            )
            for r in requests
        ]
    )


__all__ = [
    "accept_join_request",
    "cancel_my_join_request",
    "create_join_request",
    "list_my_join_requests",
    "list_team_join_requests",
    "refuse_join_request",
    "refuse_pending_join_requests",
]
