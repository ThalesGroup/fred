# Copyright Thales 2026
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
The execution plumbing an author never sees.

All I/O lives in the activity: the workflow only sequences, so an author cannot
break replay determinism because an author never writes workflow code. Nothing
in this module is exported from the package's public surface.

No heartbeat is configured: a heartbeat timeout without an activity that
actually heartbeats kills every long run. Heartbeating arrives with the
Control Plane run endpoints that report progress.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from fred_sdk.knowledge_base.client import ControlPlaneClient
from fred_sdk.knowledge_base.environment import PodEnvironment
from fred_sdk.knowledge_base.knowledge_base import KnowledgeBase
from fred_sdk.knowledge_base.routing import task_queue_for

logger = logging.getLogger(__name__)

SYNCHRONIZE_ACTIVITY = "fred_knowledge_base_synchronize"
SYNCHRONIZE_WORKFLOW = "FredKnowledgeBaseSynchronize"

_ACTIVITY_TIMEOUT = timedelta(hours=6)


@dataclass
class SynchronizeInput:
    """Identifiers only. Configuration and secrets never enter workflow history."""

    definition_id: str
    instance_id: str
    team_id: str


@workflow.defn(name=SYNCHRONIZE_WORKFLOW)
class SynchronizeWorkflow:
    @workflow.run
    async def run(self, payload: SynchronizeInput) -> str:
        # The run id comes from the workflow's own identity, so every occurrence
        # is distinguishable without anything being frozen into a schedule.
        run_id = workflow.info().run_id
        return await workflow.execute_activity(
            SYNCHRONIZE_ACTIVITY,
            args=[payload, run_id],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )


def _build_activity(knowledge_base: KnowledgeBase, control_plane: ControlPlaneClient):
    handler = knowledge_base.resolve_handler()

    @activity.defn(name=SYNCHRONIZE_ACTIVITY)
    async def synchronize(payload: SynchronizeInput, run_id: str) -> str:
        context = await control_plane.fetch_run_context(payload.definition_id, run_id)
        # A raised handler is reported by nobody here on purpose: this activity
        # runs again on retry, and reporting a terminal `failed` per attempt
        # would record a run as failed that later succeeds. Terminal failure
        # after exhausted retries is the workflow's outcome to report.
        result = await handler(context)
        await control_plane.report_result(payload.definition_id, run_id, result)
        return result.outcome.value

    return synchronize


async def serve(knowledge_base: KnowledgeBase, environment: PodEnvironment) -> None:
    """Poll this definition's queue until the process is stopped."""
    task_queue = task_queue_for(knowledge_base.id)
    client = await Client.connect(
        environment.temporal_host, namespace=environment.temporal_namespace
    )
    control_plane = ControlPlaneClient(environment)
    logger.info("Knowledge Base %s serving runs on %s", knowledge_base.id, task_queue)
    try:
        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[SynchronizeWorkflow],
            activities=[_build_activity(knowledge_base, control_plane)],
        ):
            await _run_forever()
    finally:
        await control_plane.aclose()


async def _run_forever() -> None:
    import asyncio

    await asyncio.Event().wait()
