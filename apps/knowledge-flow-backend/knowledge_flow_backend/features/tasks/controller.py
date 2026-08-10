from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    KeycloakUser,
    get_current_user,
)
from fred_core.tasks.authz import (
    authorize_task_access,
    authorize_task_mutation,
    authorize_task_stream,
    list_tasks_scoped,
)
from fred_core.tasks.models import AcknowledgeTaskResponse, TaskListResponse, TaskState
from fred_core.tasks.service import TaskNotAcknowledgeableError, TaskService
from fred_core.tasks.sse import task_event_stream, with_heartbeat
from fred_core.tasks.store import TaskNotFoundError

from knowledge_flow_backend.application_context import ApplicationContext, get_rebac_engine

logger = logging.getLogger(__name__)

# Fast-path convergence after a user-requested cancel (#2315): the OPS-04
# sweeper would only reconcile the task after its grace window plus one sweep
# interval (up to ~7 min), during which the row keeps reading "processing" and
# the half-built document's cleanup hasn't run. Polling `reconcile_task` until
# the executor reports the workflow closed drives the exact same reconciliation
# path (terminal event + `on_reconciled_terminal` cleanup) within seconds of
# the workflow actually stopping. The sweeper remains the durable backstop —
# an API restart or timeout here loses nothing.
_POST_CANCEL_RECONCILE_TIMEOUT_S = 180.0
_POST_CANCEL_RECONCILE_POLL_S = 3.0
# Strong refs so in-flight pollers aren't garbage-collected mid-loop.
_post_cancel_tasks: set[asyncio.Task] = set()


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
            if run.execution_id:
                self._schedule_post_cancel_reconcile(task_id)
            return {"task_id": task_id}

        @router.post(
            "/tasks/{task_id}/ack",
            tags=["Tasks"],
            response_model=AcknowledgeTaskResponse,
            summary="Acknowledge a task that needs attention",
        )
        async def acknowledge_task(
            task_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> AcknowledgeTaskResponse:
            run = await self._service.get_run(task_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Task not found")
            # View-level rule (§2.10) — deliberately NOT authorize_task_mutation:
            # any team reader may dismiss a teammate's failed task, not only its
            # creator or a platform admin.
            await authorize_task_access(user, run, get_rebac_engine())
            try:
                return await self._service.acknowledge(task_id, by=user.uid)
            except TaskNotFoundError:
                raise HTTPException(status_code=404, detail="Task not found")
            except TaskNotAcknowledgeableError:
                raise HTTPException(status_code=409, detail="Task does not currently need attention")

    def _schedule_post_cancel_reconcile(self, task_id: str) -> None:
        task = asyncio.create_task(self._reconcile_after_cancel(task_id))
        _post_cancel_tasks.add(task)
        task.add_done_callback(_post_cancel_tasks.discard)

    async def _reconcile_after_cancel(self, task_id: str) -> None:
        """Poll until the cancelled workflow's closure is reflected on the task.

        `reconcile_task` returns False while the executor still reports the
        workflow as running (cancellation is cooperative) and True once it drove
        the task terminal — which also fires the `on_reconciled_terminal`
        cleanup. Every error is swallowed: this is an accelerator, the sweeper
        owns correctness.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _POST_CANCEL_RECONCILE_TIMEOUT_S
        while loop.time() < deadline:
            await asyncio.sleep(_POST_CANCEL_RECONCILE_POLL_S)
            try:
                run = await self._service.get_run(task_id)
                if run is None or TaskState(run.state).is_terminal:
                    # The worker-side compensation (`emit_ingestion_task_event`
                    # with state `cancelled`) already closed the task — and ran
                    # the document cleanup with it. Nothing left to reconcile.
                    return
                if await self._service.reconcile_task(task_id):
                    return
            except Exception:
                logger.warning(
                    "[TASKS] post-cancel reconcile poll failed for task_id=%s; leaving it to the sweeper",
                    task_id,
                    exc_info=True,
                )
                return
        logger.info(
            "[TASKS] post-cancel reconcile timed out for task_id=%s; sweeper will finish it",
            task_id,
        )
