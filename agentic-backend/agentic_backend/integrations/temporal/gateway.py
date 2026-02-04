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

"""
Thin gateway around TemporalClientProvider.

Responsibilities
----------------
- Provide a single entry point to start a workflow (submit) and fetch status.
- Keep API surface minimal so it can be used by LLM tools or other services
  without dragging LangChain/LangGraph dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from fred_core.scheduler import TemporalClientProvider
from temporalio.client import WorkflowHandle

from agentic_backend.scheduler.agent_contracts import (
    AgentContextRefsV1,
    AgentInputArgsV1,
)

logger = logging.getLogger(__name__)


@dataclass
class TemporalSubmission:
    workflow_id: str
    target_agent: str
    mode: Optional[str] = None  # optional, caller-controlled label


@dataclass
class TemporalStatus:
    workflow_id: str
    status: str
    final_summary: Optional[str] = None
    error: Optional[str] = None


class TemporalGateway:
    """Single-responsibility wrapper for Temporal operations used by agents."""

    def __init__(self, *, provider: TemporalClientProvider, task_queue: str):
        self._provider = provider
        self._task_queue = task_queue

    async def submit(
        self,
        *,
        request_text: str,
        project_id: Optional[str],
        target_agent: str,
        user_id: Optional[str],
    ) -> TemporalSubmission:
        client = await self._provider.get_client()

        tid = str(uuid4())
        workflow_id = f"delegate-{tid}"

        payload = AgentInputArgsV1(
            task_id=tid,
            target_ref=target_agent,
            user_id=user_id,
            request_text=request_text,
            context=AgentContextRefsV1(project_id=project_id),
            parameters={},
        )

        await client.start_workflow(
            "AgentWorkflow",
            payload,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        logger.info(
            "[TemporalGateway] Started workflow %s (target_agent=%s)",
            workflow_id,
            target_agent,
        )
        return TemporalSubmission(
            workflow_id=workflow_id, target_agent=target_agent, mode=None
        )

    async def status(self, *, workflow_id: str) -> TemporalStatus:
        client = await self._provider.get_client()
        handle: WorkflowHandle = client.get_workflow_handle(workflow_id)

        try:
            desc = await handle.describe()
            status_obj = getattr(desc, "status", None)
            status = status_obj.name if hasattr(status_obj, "name") else str(status_obj)
            final_summary = None
            if status == "COMPLETED":
                try:
                    result = await handle.result()
                    final_summary = getattr(result, "final_summary", None) or str(
                        result
                    )
                except Exception as exc:  # pragma: no cover
                    final_summary = f"(résumé indisponible: {exc})"
            return TemporalStatus(
                workflow_id=workflow_id, status=status, final_summary=final_summary
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "[TemporalGateway] Status failed for %s: %s", workflow_id, exc
            )
            return TemporalStatus(
                workflow_id=workflow_id, status="ERROR", error=str(exc)
            )

    # No routing logic here: caller chooses target_agent.
