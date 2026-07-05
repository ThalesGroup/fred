from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    KeycloakUser,
    get_current_user,
)
from fred_core.tasks.authz import (
    authorize_task_mutation,
    authorize_task_stream,
    list_tasks_scoped,
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
            return await list_tasks_scoped(self._service, get_rebac_engine(), user, scope=scope, team_id=team_id, kind=kind, state=state)

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
            await authorize_task_stream(user, run, get_rebac_engine())

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
            await authorize_task_mutation(user, run, get_rebac_engine())
            await self._service.cancel(task_id)
            return {"task_id": task_id}
