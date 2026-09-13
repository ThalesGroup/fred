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
The workflow, held apart from everything it must not reach.

Replay determinism is the rule here: no clock, no randomness, no I/O — all of
that belongs to the activity in `worker.py`. Nothing enforces it automatically,
because `fred_sdk` is passed through the sandbox wholesale (the reason is in
`worker.build_workflow_runner`), so this module stays stdlib-only and small
enough that the rule can be checked by eye. Authors never write workflow code,
so nothing an author writes depends on what is in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

SYNCHRONIZE_ACTIVITY = "fred_knowledge_base_synchronize"
SYNCHRONIZE_WORKFLOW = "FredKnowledgeBaseSynchronize"

# No heartbeat is configured: a heartbeat timeout without an activity that
# actually heartbeats kills every long run. Heartbeating arrives with the
# Control Plane run endpoints that report progress.
ACTIVITY_TIMEOUT = timedelta(hours=6)

# Used only when a dispatcher sends no budget of its own. The real value is
# Fred's, read from its configuration and carried on the input below — a budget
# frozen into a third-party image would be a number Fred could never change.
FALLBACK_MAX_ATTEMPTS = 2


@dataclass
class SynchronizeInput:
    """What a run is told about itself.

    Identifiers, and the attempt budget Fred set. No configuration and no
    secret: workflow history is replicated and retained for as long as a
    retention policy says, so what enters it must be safe to keep for ever.
    """

    definition_id: str
    instance_id: str
    team_id: str
    max_attempts: int = FALLBACK_MAX_ATTEMPTS


@workflow.defn(name=SYNCHRONIZE_WORKFLOW)
class SynchronizeWorkflow:
    @workflow.run
    async def run(self, payload: SynchronizeInput) -> str:
        # Both come from the workflow's own identity, so every occurrence is
        # distinguishable without anything being frozen into a schedule. They
        # travel as arguments rather than being read from ambient context in the
        # activity: the workflow is the side that knows them for certain.
        info = workflow.info()
        return await workflow.execute_activity(
            SYNCHRONIZE_ACTIVITY,
            args=[payload, info.run_id, info.workflow_id],
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            # Without a policy Temporal retries an activity for ever, so a
            # handler that fails the same way every time never reaches the
            # terminal failure the contract promises. Bounding the attempts is
            # what makes exhaustion — and therefore a failed run — reachable.
            # Retried at the activity, not at the workflow: a workflow retry
            # would mint a new run id per attempt, and one run would be reported
            # to Fred as several.
            retry_policy=RetryPolicy(maximum_attempts=payload.max_attempts),
        )
