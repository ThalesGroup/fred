from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    get_current_user,
    require_task_access,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.tasks.authz import authorize_task_stream, list_tasks_scoped
from fred_core.tasks.models import (
    StartTaskRequest,
    StartTaskResponse,
    TaskListResponse,
)
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import task_event_stream, with_heartbeat

from control_plane_backend.app.dependencies import get_application_container


def _get_task_service(request: Request) -> TaskService:
    container = get_application_container(request)
    return container.get_task_service()


def _get_rebac_engine(request: Request) -> RebacEngine:
    container = get_application_container(request)
    return container.get_rebac_engine()


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
        return await list_tasks_scoped(
            service, rebac, user, scope=scope, team_id=team_id, kind=kind, state=state
        )

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
        await authorize_task_stream(user, run, rebac)

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
