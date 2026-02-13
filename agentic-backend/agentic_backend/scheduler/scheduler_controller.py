# Copyright Thales 2025
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
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fred_core import KeycloakUser, get_current_user, raise_internal_error
from fred_core.scheduler import TemporalClientProvider

from agentic_backend.application_context import get_task_store
from agentic_backend.scheduler.scheduler_service import AgentTaskService
from agentic_backend.scheduler.task_structures import (
    AgentTaskRecordV1,
    AgentTaskStatus,
    SubmitAgentTaskRequest,
    SubmitAgentTaskResponse,
)

logger = logging.getLogger(__name__)


class AgentTasksController:
    """
    FastAPI Controller for managing Agent Tasks.

    Coordinates between the HTTP layer and the AgentTaskService.
    """

    def __init__(
        self,
        router: APIRouter,
        temporal_client_provider: TemporalClientProvider,
        task_queue: str,
    ):
        # Initialize the Service which handles the business logic and Temporal interaction
        self.service = AgentTaskService(
            temporal_client_provider=temporal_client_provider,
            temporal_task_queue=task_queue,
            task_store=get_task_store(),
            workflow_name="AgentWorkflow",
            workflow_id_prefix="agent",
        )

        @router.post(
            "/v1/agent-tasks",
            tags=["AgentTasks"],
            response_model=SubmitAgentTaskResponse,
            summary="Submit a new agent task",
            description="Creates a task record and triggers a Temporal workflow execution.",
        )
        async def submit_agent_task(
            req: SubmitAgentTaskRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                # We delegate to the service to handle persistence and workflow startup
                record = await self.service.submit(
                    user_id=user.uid,
                    target_agent=req.target_agent,
                    request_text=req.request_text,
                    context=req.context,
                    parameters=req.parameters,
                    task_id=req.task_id,
                )

                return SubmitAgentTaskResponse(
                    task_id=record.task_id,
                    status=record.status,
                    workflow_id=record.workflow_id,
                    run_id=record.run_id,
                )
            except Exception as e:
                # Centralized error handling helper
                raise_internal_error(logger, "Failed to submit agent task", e)

        @router.get(
            "/v1/agent-tasks",
            tags=["AgentTasks"],
            response_model=List[AgentTaskRecordV1],
            summary="List current user's agent tasks",
            description="Returns a list of tasks owned by the authenticated user with optional filters.",
        )
        async def list_agent_tasks(
            limit: int = Query(default=20, ge=1, le=100),
            status: Optional[AgentTaskStatus] = Query(default=None),
            target_agent: Optional[str] = Query(default=None),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                # Convert single status query to sequence for the store filter
                statuses = [status] if status else None

                return self.service.list_for_user(
                    user_id=user.uid,
                    limit=limit,
                    statuses=statuses,
                    target_agent=target_agent,
                )
            except Exception as e:
                raise_internal_error(logger, "Failed to list agent tasks", e)
