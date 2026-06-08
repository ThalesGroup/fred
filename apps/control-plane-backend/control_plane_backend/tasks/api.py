from __future__ import annotations

import logging
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    KeycloakUser,
    TeamPermission,
    get_current_user,
    require_admin,
    require_task_access,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.tasks.bus import IEventBus
from fred_core.tasks.models import (
    StartTaskRequest,
    StartTaskResponse,
    TaskListResponse,
    TaskState,
)
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import with_heartbeat

from control_plane_backend.app.dependencies import get_application_container

logger = logging.getLogger(__name__)


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
    ) -> StartTaskResponse:
        require_admin(user)
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
            require_admin(user)
            return await service.list_tasks(kind=kind, state=state)
        # scope == "team"
        if not team_id:
            raise HTTPException(
                status_code=400, detail="team_id is required for scope=team"
            )
        if "admin" not in user.roles:
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
    ) -> StreamingResponse:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        require_task_access(user, run.created_by)

        last_event_id = request.headers.get("Last-Event-ID")
        try:
            after_seq = int(last_event_id) if last_event_id else -1
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be a non-negative integer"
            )

        async def event_stream() -> AsyncIterator[str]:
            replayed = await service.replay(task_id, after_seq=after_seq)
            for event in replayed:
                yield f"id: {event.seq}\ndata: {event.model_dump_json()}\n\n"
                if event.state.is_terminal:
                    return

            if TaskState(run.state).is_terminal:
                return

            bus: IEventBus = service.bus
            async for live_event in bus.subscribe(task_id):
                if await request.is_disconnected():
                    break
                yield f"id: {live_event.seq}\ndata: {live_event.model_dump_json()}\n\n"
                if live_event.state.is_terminal:
                    break

        return StreamingResponse(
            with_heartbeat(event_stream()), media_type="text/event-stream"
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
