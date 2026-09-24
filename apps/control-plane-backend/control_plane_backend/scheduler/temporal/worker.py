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

from __future__ import annotations

import logging

from fred_core.common import TemporalSchedulerConfig
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.temporal.activities import (
    LifecycleActivities,
)
from control_plane_backend.scheduler.temporal.schedule_manager import (
    ensure_lifecycle_schedule,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.scheduler.temporal.workflow import LifecycleManagerWorkflow

logger = logging.getLogger(__name__)


async def run_worker(
    config: TemporalSchedulerConfig,
    lifecycle_deps: LifecycleActionDependencies,
) -> None:
    """
    Connect to Temporal and run the control-plane lifecycle worker.

    Why this function exists:
    - the Temporal worker needs one bootstrap path that binds workflows and
      activities to explicit lifecycle dependencies

    How to use it:
    - call from `main_worker.py` after building the shared container
    - pass the worker-scoped lifecycle dependency bundle built from that container

    Example:
    - `await run_worker(configuration.scheduler.temporal, lifecycle_deps)`
    """
    logger.info(
        "[TEMPORAL] Connecting to Temporal at %s (namespace=%s)",
        config.host,
        config.namespace,
    )
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
        data_converter=pydantic_data_converter,
    )

    scheduled_input = LifecycleManagerInput(
        dry_run=False,
        batch_size=100,
    )
    schedule_id = await ensure_lifecycle_schedule(client, config, scheduled_input)
    logger.info("[TEMPORAL] Lifecycle schedule ready: %s", schedule_id)

    logger.info(
        "[TEMPORAL] Connected. Registering worker on queue '%s'",
        config.task_queue,
    )
    activities = LifecycleActivities(lifecycle_deps)
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[LifecycleManagerWorkflow],
        activities=[
            activities.list_conversation_candidates,
            activities.delete_conversation,
            activities.list_wiki_proposal_candidates,
            activities.reject_wiki_proposal,
        ],
    )

    logger.info("[TEMPORAL] Control-plane Temporal worker running.")
    await worker.run()
