import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fred_core import (
    KeycloakUser,
    get_current_user,
    oauth2_scheme,
    raise_internal_error,
)
from fred_core.scheduler import (
    AgentCallTask,
    BaseScheduler,
    InMemoryScheduler,
    TemporalScheduler,
)

from agentic_backend.application_context import get_configuration
from agentic_backend.core.agents.execution_state import build_agent_conversation_payload
from agentic_backend.scheduler.scheduler_structures import (
    AgentTaskProgressRequest,
    AgentTaskProgressResponse,
    RunAgentTaskRequest,
    RunAgentTaskResponse,
)

logger = logging.getLogger(__name__)


class SchedulerController:
    def __init__(self, router: APIRouter):
        config = get_configuration().scheduler
        if config.backend.lower() == "memory":
            self.scheduler: BaseScheduler = InMemoryScheduler()
        elif config.backend.lower() == "temporal":
            self.scheduler = TemporalScheduler(config.temporal)
        else:
            raise ValueError(f"Unsupported scheduler backend: {config.backend}")

        @router.post(
            "/scheduler/agent-tasks",
            tags=["Scheduler"],
            response_model=RunAgentTaskResponse,
            summary="Submit an agent task to the scheduler",
        )
        async def run_agent_task(
            req: RunAgentTaskRequest,
            user: KeycloakUser = Depends(get_current_user),
            token: str | None = Depends(oauth2_scheme),
        ):
            task_id = req.task_id or f"agent-task-{uuid4()}"
            context = dict(req.context)
            if token:
                context["access_token"] = token
                context.setdefault("user_groups", user.groups)
                context.setdefault("user_id", user.uid)
            conversation = req.conversation
            if conversation is None:
                try:
                    conversation = build_agent_conversation_payload(
                        question=req.payload.get("question"),
                        payload=req.payload,
                    )
                except ValueError:
                    conversation = None

            task = AgentCallTask(
                task_id=task_id,
                workflow_type=req.workflow_type,
                task_queue=req.task_queue,
                caller_actor=user.uid,
                target_agent=req.target_agent,
                session_id=req.session_id,
                request_id=req.request_id,
                payload=req.payload,
                context=context,
                conversation=conversation,
            )

            try:
                logger.info("[SCHEDULER] Submitting agent task: %s", task)
                handle = await self.scheduler.start_task(task)
            except Exception as e:
                raise_internal_error(logger, "Failed to submit agent task", e)

            return RunAgentTaskResponse(
                status="queued",
                task_id=task_id,
                workflow_id=handle.workflow_id,
                run_id=handle.run_id,
            )

        @router.post(
            "/scheduler/agent-tasks/progress",
            tags=["Scheduler"],
            response_model=AgentTaskProgressResponse,
            summary="Get progress for a scheduled agent task",
        )
        async def get_agent_task_progress(
            req: AgentTaskProgressRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                if req.workflow_id:
                    progress = await self.scheduler.get_progress(
                        workflow_id=req.workflow_id,
                        run_id=req.run_id,
                    )
                    return AgentTaskProgressResponse(
                        task_id=req.task_id,
                        workflow_id=req.workflow_id,
                        run_id=req.run_id,
                        progress=progress,
                    )

                if req.task_id:
                    handle = self.scheduler.get_handle_for_task(req.task_id)
                    progress = await self.scheduler.get_progress_for_task(req.task_id)
                    return AgentTaskProgressResponse(
                        task_id=req.task_id,
                        workflow_id=handle.workflow_id if handle else None,
                        run_id=handle.run_id if handle else None,
                        progress=progress,
                    )

                handle = self.scheduler.get_last_handle_for_actor(user.uid)
                if not handle:
                    raise HTTPException(
                        status_code=404, detail="No workflow found for caller"
                    )

                progress = await self.scheduler.get_progress_for_actor(user.uid)
                return AgentTaskProgressResponse(
                    task_id=None,
                    workflow_id=handle.workflow_id,
                    run_id=handle.run_id,
                    progress=progress,
                )
            except HTTPException:
                raise
            except Exception as e:
                raise_internal_error(logger, "Failed to fetch agent task progress", e)
