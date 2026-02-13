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
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

from agentic_backend.scheduler.agent_contracts import (
    AgentInputArgsV1,
    AgentResultStatus,
    AgentResultV1,
    ProgressEventV1,
)


@workflow.defn(name="AgentWorkflow")
class AgentWorkflow:
    @workflow.run
    async def run(self, input: AgentInputArgsV1) -> AgentResultV1:
        # 1. Define Activity Options
        # We allow long execution (e.g. 1 hour) but require heartbeats every minute
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            non_retryable_error_types=["ValueError", "AgentTaskForbiddenError"],
        )

        # 2. Run the Agent Activity
        # We wrap this in a try/except to handle cancellations or timeouts
        try:
            result = await workflow.execute_activity(
                "run_langgraph_activity",
                input,
                start_to_close_timeout=timedelta(hours=1),
                heartbeat_timeout=timedelta(minutes=1),
                retry_policy=retry_policy,
            )
            return result
        except ActivityError as e:
            # Logging inside the Temporal workflow sandbox can trigger restricted
            # handlers (e.g., OpenSearch). Keep side effects minimal here.
            return AgentResultV1(
                status=AgentResultStatus.FAILED,
                final_summary=f"Activity failed: {str(e.__cause__ or e)}",
            )
        except Exception as e:
            # Catch-all for other workflow-level issues (logging avoided in sandbox)
            return AgentResultV1(
                status=AgentResultStatus.FAILED,
                final_summary=f"Unexpected workflow error: {str(e)}",
            )

    @workflow.query
    def get_progress(self) -> ProgressEventV1:
        """
        Query allowing the API to ask "Where are we?"
        It returns the details from the last Heartbeat.
        """
        # Temporal Python automatically tracks the last heartbeat details
        # if the activity failed/timed out, but for live queries,
        # you typically access internal state.
        # *Simple approach*: The activity is running, so query might rely on
        # external DB status in this specific Monolithic pattern.
        # *Advanced*: Use Signals to update workflow state.

        return ProgressEventV1(label="Running...", phase="unknown")
