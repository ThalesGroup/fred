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
import logging

from temporalio import activity

from agentic_backend.scheduler.agent_contracts import AgentInputV1, AgentResultV1
from agentic_backend.scheduler.temporal.agent_task_runner import get_runner

logger = logging.getLogger(__name__)


@activity.defn(name="run_langgraph_activity")
async def run_langgraph_activity(input: AgentInputV1) -> AgentResultV1:
    """
    Temporal Activity entry point.
    It delegates all logic to the AgentTaskRunner.
    """
    logger.info(
        f"[ACTIVITY] Starting task {input.task_id} for agent {input.target_agent}"
    )

    # Fetch the singleton runner
    runner = await get_runner()

    # Execute the task
    return await runner.run_temporal_task(input)
