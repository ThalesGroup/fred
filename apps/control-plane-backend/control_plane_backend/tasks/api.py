from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
    get_current_user,
    require_task_access,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.tasks.models import (
    StartTaskRequest,
    StartTaskResponse,
    TaskListResponse,
)
from fred_core.tasks.orm_models import TaskRunRow
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import task_event_stream, with_heartbeat

from control_plane_backend.app.dependencies import get_application_container


def _get_task_service(request: Request) -> TaskService:
    container = get_application_container(request)
    return container.get_task_service()


def _get_rebac_engine(request: Request) -> RebacEngine:
    container = get_application_container(request)
    return container.get_rebac_engine()


async def _authorize_task_stream(
    user: KeycloakUser, run: TaskRunRow, rebac: RebacEngine
) -> None:
    """Authorize streaming a task's events by the SAME rule that governs listing it
    (CTRLP-12): its creator, a platform admin, or a member with CAN_READ_MEMBERS on
    the task's team. `GET /tasks` exposes erasure tasks to platform/team admins even
    though they are created with the affected user's uid, so streaming must accept
    the same callers — otherwise an admin can see a scheduled erasure but not watch
    it run.

    Raises AuthorizationError/HTTPException when denied.
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


def build_tasks_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["tasks"])

    @router.post("/tasks", status_code=202, response_model=StartTaskResponse)
    async def start_task(
        body: StartTaskRequest,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> StartTaskResponse:
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )
        return await service.start(body, created_by=user.uid)

    @router.get("/tasks", response_model=TaskListResponse)
    async def list_tasks(
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
        scope: str = Query(default="platform", pattern="^(platform|team|user)$"),
        team_id: str | None = Query(default=None),
        kind: str | None = Query(default=None),
        state: str | None = Query(default=None),
    ) -> TaskListResponse:
        if scope == "user":
            # No role required — returns only tasks created by the caller.
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

    @router.get("/tasks/{task_id}/events")
    async def stream_task_events(
        task_id: str,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> StreamingResponse:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await _authorize_task_stream(user, run, rebac)

        last_event_id = request.headers.get("Last-Event-ID")
        try:
            after_seq = int(last_event_id) if last_event_id else -1
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be a non-negative integer"
            )

        return StreamingResponse(
            with_heartbeat(
                task_event_stream(
                    service,
                    task_id,
                    after_seq=after_seq,
                    is_disconnected=request.is_disconnected,
                )
            ),
            media_type="text/event-stream",
        )

    @router.post("/tasks/{task_id}/cancel", status_code=202)
    async def cancel_task(
        task_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
    ) -> dict:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        require_task_access(user, run.created_by)
        await service.cancel(task_id)
        return {"task_id": task_id}

    return router
