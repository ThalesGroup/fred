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

"""Canonical task visibility/authorization, shared by every backend router.

The rule must be identical wherever tasks are exposed: what you can *list* you can
*stream*, and vice-versa. Keeping it here — instead of copied into each router —
is deliberate: a per-router copy is exactly what let stream authz drift stricter
than list authz before (CTRLP-12). Control-plane and Knowledge-Flow both delegate
here.
"""

from __future__ import annotations

from fastapi import HTTPException

from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
    RebacEngine,
    TeamPermission,
)
from fred_core.security.structure import KeycloakUser
from fred_core.tasks.models import TaskListResponse
from fred_core.tasks.orm_models import TaskRunRow
from fred_core.tasks.service import TaskService


async def authorize_task_stream(
    user: KeycloakUser, run: TaskRunRow, rebac: RebacEngine
) -> None:
    """Authorize streaming a task's events by the SAME rule that governs listing it:
    its creator, a platform admin, or a member with CAN_READ_MEMBERS on the task's
    team. Tasks (e.g. erasure) are created with the affected user's uid, so an admin
    who can see one in the list must also be able to stream it.

    Raises AuthorizationError/HTTPException (→ 403) when denied.
    """
    # Creator, or the legacy system "admin" role fast-path (internal operations).
    if "admin" in user.roles or (
        run.created_by is not None and run.created_by == user.uid
    ):
        return
    if await rebac.has_user_permission(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    ):
        return
    if run.team_id:
        # Raises AuthorizationError (403) when the caller lacks team read.
        await rebac.check_user_team_permission_or_raise(
            user, TeamPermission.CAN_READ_MEMEBERS, team_id=run.team_id
        )
        return
    raise HTTPException(status_code=403, detail="Not authorized to stream this task")


async def list_tasks_scoped(
    service: TaskService,
    rebac: RebacEngine,
    user: KeycloakUser,
    *,
    scope: str,
    team_id: str | None,
    kind: str | None,
    state: str | None,
) -> TaskListResponse:
    """The single owner of the GET /tasks scope → authz → query rule (RFC §7.2).

    - ``user``: no role required — only the caller's own tasks (terminal ones
      hidden unless a state filter is given).
    - ``platform``: requires ``can_manage_platform``.
    - ``team``: requires ``team_id`` and either ``can_manage_platform`` or
      ``CAN_READ_MEMBERS`` on that team.

    ``scope`` is assumed already validated to ``platform|team|user`` by the route.
    """
    if scope == "user":
        return await service.list_tasks(
            created_by=user.uid,
            kind=kind,
            state=state,
            exclude_terminal=(state is None),
        )
    if scope == "platform":
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )
        return await service.list_tasks(kind=kind, state=state)
    # scope == "team"
    if not team_id:
        raise HTTPException(
            status_code=400, detail="team_id is required for scope=team"
        )
    if not await rebac.has_user_permission(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    ):
        await rebac.check_user_team_permission_or_raise(
            user, TeamPermission.CAN_READ_MEMEBERS, team_id=team_id
        )
    return await service.list_tasks(team_id=team_id, kind=kind, state=state)
