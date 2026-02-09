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
from typing import List, Optional, Sequence
from uuid import uuid4

from fred_core.scheduler import TemporalClientProvider
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy

from agentic_backend.scheduler.agent_contracts import (
    AgentContextRefsV1,
    AgentInputArgsV1,
)
from agentic_backend.scheduler.store.base_task_store import BaseAgentTaskStore
from agentic_backend.scheduler.task_structures import AgentTaskRecordV1, AgentTaskStatus

logger = logging.getLogger(__name__)


class AgentTaskService:
    """
    Business logic layer for Agent Tasks.

    Responsibilities:
    - Generating unique Task IDs and Workflow IDs.
    - Synchronizing the Postgres Task Store with Temporal execution.
    - Handling Temporal startup failures gracefully.
    """

    def __init__(
        self,
        *,
        temporal_client_provider: TemporalClientProvider,
        temporal_task_queue: str,
        task_store: BaseAgentTaskStore,
        workflow_name: str = "AgentWorkflow",
        workflow_id_prefix: str = "agent",
    ) -> None:
        self._client_provider = temporal_client_provider
        self._task_queue = temporal_task_queue
        self._store = task_store
        self._workflow_name = workflow_name
        self._workflow_id_prefix = workflow_id_prefix

    async def _client(self) -> Client:
        """Helper to get the initialized Temporal client."""
        return await self._client_provider.get_client()

    async def submit(
        self,
        *,
        user_id: str,
        target_agent: str,
        request_text: str,
        context: AgentContextRefsV1,
        parameters: dict,
        task_id: Optional[str] = None,
    ) -> AgentTaskRecordV1:
        """
        Submits a new task by creating a DB record and starting a Temporal workflow.
        """
        client = await self._client()

        # 1. Generate Identifiers
        # Use client-provided task_id for idempotency if available
        tid = task_id or f"{uuid4()}"
        workflow_id = f"{self._workflow_id_prefix}-{tid}"

        # 2. Construct the Typed Input for Temporal
        agent_input = AgentInputArgsV1(
            target_ref=target_agent,
            target_kind="agent",
            task_id=tid,
            user_id=user_id,
            request_text=request_text,
            context=context,
            parameters=parameters,
        )

        # 3. Create the Database Record (Immediate persistence)
        # We set status to QUEUED and run_id to None initially
        await self._store.create(
            task_id=tid,
            user_id=user_id,
            target_agent=target_agent,
            request_text=request_text,
            workflow_id=workflow_id,
            run_id=None,
            context=context,
            parameters=parameters,
        )

        try:
            # 4. Start the Temporal Workflow
            # Note: We pass the pydantic model directly;
            # the Temporal DataConverter will serialize it to JSON.
            handle = await client.start_workflow(
                self._workflow_name,
                agent_input,
                id=workflow_id,
                task_queue=self._task_queue,
                # Prevents accidental double-execution for the same Task ID
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )

            # 5. Update the DB with the assigned Temporal Run ID
            await self._store.update_handle(
                task_id=tid, workflow_id=workflow_id, run_id=handle.run_id
            )

            logger.info(
                "[AGENT_SERVICE] Started workflow %s (run_id: %s) for task %s",
                workflow_id,
                handle.run_id,
                tid,
            )

        except Exception as e:
            logger.exception(
                "[AGENT_SERVICE] Failed to start Temporal workflow for task %s", tid
            )

            # 6. Mark as FAILED in DB so the UI doesn't show it as stuck in QUEUED
            await self._store.update_status(
                task_id=tid,
                status=AgentTaskStatus.FAILED,
                error_json={
                    "error_code": "TEMPORAL_START_FAILED",
                    "message": str(e),
                    "retryable": False,
                },
            )
            raise

        # Return the most up-to-date record
        return await self._store.get(tid)

    async def list_for_user(
        self,
        *,
        user_id: str,
        limit: int = 20,
        statuses: Optional[Sequence[AgentTaskStatus]] = None,
        target_agent: Optional[str] = None,
    ) -> List[AgentTaskRecordV1]:
        """Fetch tasks for the authenticated user from the store."""
        return await self._store.list_for_user(
            user_id=user_id,
            limit=limit,
            statuses=statuses,
            target_agent=target_agent,
        )
