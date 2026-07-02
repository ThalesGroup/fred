from __future__ import annotations

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
from fred_core.tasks.models import TaskListResponse
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import task_event_stream, with_heartbeat

from knowledge_flow_backend.application_context import ApplicationContext, get_rebac_engine


class TasksController:
    def __init__(self, router: APIRouter) -> None:
        app_context = ApplicationContext.get_instance()
        self._service: TaskService = app_context.get_task_service()

        @router.get(
            "/tasks",
            tags=["Tasks"],
            response_model=TaskListResponse,
            summary="List tasks (RFC §7.2 — platform, team, or user scope)",
        )
        async def list_tasks(
            user: KeycloakUser = Depends(get_current_user),
            scope: str = Query(default="platform", pattern="^(platform|team|user)$"),
            team_id: str | None = Query(default=None),
            kind: str | None = Query(default=None),
            state: str | None = Query(default=None),
        ) -> TaskListResponse:
            rebac = get_rebac_engine()
            if scope == "user":
                # No role required — returns only tasks created by the caller.
                # exclude_terminal=True unless the caller explicitly filters by state.
                return await self._service.list_tasks(created_by=user.uid, kind=kind, state=state, exclude_terminal=(state is None))
            if scope == "platform":
                await rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
                return await self._service.list_tasks(kind=kind, state=state)
            # scope == "team"
            if not team_id:
                raise HTTPException(status_code=400, detail="team_id is required for scope=team")
            if not await rebac.has_user_permission(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID):
                await rebac.check_user_team_permission_or_raise(user, TeamPermission.CAN_READ_MEMEBERS, team_id=team_id)
            return await self._service.list_tasks(team_id=team_id, kind=kind, state=state)

        @router.get(
            "/tasks/{task_id}/events",
            tags=["Tasks"],
            summary="Stream task progress events (SSE)",
        )
        async def stream_task_events(
            task_id: str,
            request: Request,
            user: KeycloakUser = Depends(get_current_user),
        ) -> StreamingResponse:
            service = self._service
            run = await service.get_run(task_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Task not found")
            require_task_access(user, run.created_by)

            last_event_id = request.headers.get("Last-Event-ID")
            try:
                after_seq = int(last_event_id) if last_event_id else -1
            except ValueError:
                raise HTTPException(status_code=400, detail="Last-Event-ID must be a non-negative integer")

            return StreamingResponse(
                with_heartbeat(task_event_stream(service, task_id, after_seq=after_seq, is_disconnected=request.is_disconnected)),
                media_type="text/event-stream",
            )

        @router.post(
            "/tasks/{task_id}/cancel",
            tags=["Tasks"],
            status_code=202,
            summary="Request cooperative cancellation of a running task",
        )
        async def cancel_task(
            task_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> dict:
            run = await self._service.get_run(task_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Task not found")
            require_task_access(user, run.created_by)
            await self._service.cancel(task_id)
            return {"task_id": task_id}
