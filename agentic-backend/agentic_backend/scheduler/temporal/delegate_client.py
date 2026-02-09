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

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from fred_core.scheduler import TemporalClientProvider
from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy

from agentic_backend.application_context import get_configuration
from agentic_backend.scheduler.agent_contracts import (
    AgentContextRefsV1,
    AgentInputArgsV1,
    AgentResultStatus,
    AgentResultV1,
    ProgressEventV1,
)

logger = logging.getLogger(__name__)


class TemporalAgentInvoker:
    """Lightweight helper to run another LangGraph agent through Temporal.

    Designed for in-agent delegation: start a child `AgentWorkflow`, keep the
    parent activity alive with heartbeats, and return both the result and the
    spawned workflow id.
    """

    def __init__(
        self,
        *,
        workflow_name: str = "AgentWorkflow",
        workflow_id_prefix: str = "delegate",
        default_heartbeat_interval: float = 25.0,
    ) -> None:
        cfg = get_configuration().scheduler
        if cfg.backend != "temporal":
            raise RuntimeError(
                f"TemporalAgentInvoker requires Temporal backend; current={cfg.backend}"
            )

        self._temporal_config = cfg.temporal
        self._client_provider = TemporalClientProvider(self._temporal_config)
        self._workflow_name = workflow_name
        self._workflow_id_prefix = workflow_id_prefix
        self._heartbeat_interval = default_heartbeat_interval

    async def execute_agent(
        self,
        *,
        target_agent: str,
        request_text: str,
        user_id: Optional[str],
        context: Optional[AgentContextRefsV1] = None,
        parameters: Optional[Dict[str, Any]] = None,
        heartbeat_label: str = "waiting_for_delegate",
        heartbeat_interval: Optional[float] = None,
    ) -> Tuple[AgentResultV1, str]:
        """Start the target agent as a Temporal workflow and wait for completion.

        Returns:
            (AgentResultV1, workflow_id)
        """

        client = await self._client_provider.get_client()
        tid = str(uuid4())
        workflow_id = f"{self._workflow_id_prefix}-{tid}"

        payload = AgentInputArgsV1(
            task_id=tid,
            target_ref=target_agent,
            user_id=user_id,
            request_text=request_text,
            context=context or AgentContextRefsV1(),
            parameters=parameters or {},
        )

        handle = await client.start_workflow(
            self._workflow_name,
            payload,
            id=workflow_id,
            task_queue=self._temporal_config.task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )

        wait_seconds = heartbeat_interval or self._heartbeat_interval
        try:
            result = await self._wait_for_result(
                handle=handle,
                heartbeat_label=heartbeat_label,
                every_seconds=wait_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "[DELEGATE] Workflow %s failed for agent %s", workflow_id, target_agent
            )
            return (
                AgentResultV1(
                    status=AgentResultStatus.FAILED,
                    final_summary=str(exc),
                    checkpoint_ref=tid,
                ),
                workflow_id,
            )

        return result, workflow_id

    async def _wait_for_result(
        self,
        *,
        handle: WorkflowHandle[Any, AgentResultV1],
        heartbeat_label: str,
        every_seconds: float,
    ) -> AgentResultV1:
        """Wait for workflow result while sending periodic heartbeats."""

        task = asyncio.create_task(handle.result())

        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(task), timeout=every_seconds
                )
            except asyncio.TimeoutError:
                self._heartbeat(label=heartbeat_label, workflow_id=handle.id)
                continue

    def _heartbeat(self, *, label: str, workflow_id: str) -> None:
        """Best-effort heartbeat to keep the parent Temporal activity alive."""

        try:
            activity.info()
            activity.heartbeat(
                ProgressEventV1(
                    label=label,
                    phase="delegated_agent",
                    percent=None,
                    extras={"workflow_id": workflow_id},
                ).model_dump(mode="json")
            )
        except RuntimeError:
            # Not running inside a Temporal activity; safe to ignore.
            logger.debug(
                "[DELEGATE] Heartbeat skipped (no Temporal activity context) id=%s",
                workflow_id,
            )
