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

from temporalio.client import Client
from temporalio.worker import Worker

from fred_core.scheduler import TemporalSchedulerConfig

from agentic_backend.scheduler.temporal.activities import run_agent_task
from agentic_backend.scheduler.temporal.workflow import AgentWorkflow

logger = logging.getLogger(__name__)


async def run_worker(config: TemporalSchedulerConfig) -> None:
    logger.info("Connecting to Temporal at %s (namespace=%s)", config.host, config.namespace)
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
    )
    logger.info("Temporal connected. Registering agent worker on queue '%s'", config.task_queue)

    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[AgentWorkflow],
        activities=[run_agent_task],
    )
    logger.info("Agent Temporal worker running.")
    await worker.run()
