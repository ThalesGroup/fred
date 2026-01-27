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

# Preload pydantic_core to avoid late imports inside the Temporal workflow sandbox.
import pydantic_core  # noqa: F401
from fred_core import TemporalSchedulerConfig
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from agentic_backend.scheduler.temporal.agent_activity import run_langgraph_activity
from agentic_backend.scheduler.temporal.workflow import AgentWorkflow

logger = logging.getLogger(__name__)


async def run_worker(config: TemporalSchedulerConfig) -> None:
    logger.info(
        "[TEMPORAL] Connecting to Temporal at %s (namespace=%s)",
        config.host,
        config.namespace,
    )

    # 3. Connect Client
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
        data_converter=pydantic_data_converter,
    )

    logger.info(
        "[TEMPORAL] Temporal connected. Registering agent worker on queue '%s'",
        config.task_queue,
    )

    # 4. Register the new Workflow and the refined Activity
    # The Worker will now be able to execute the "run_langgraph_activity"
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[AgentWorkflow],
        activities=[run_langgraph_activity],
    )

    logger.info("[TEMPORAL] Agent Temporal worker (LangGraph-optimized) running.")

    # This runs until the process is terminated
    await worker.run()
