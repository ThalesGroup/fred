from __future__ import annotations

import logging

from fred_core.common import TemporalSchedulerConfig
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from control_plane_backend.scheduler.temporal.activities import (
    delete_conversation,
    list_conversation_candidates,
)
from control_plane_backend.scheduler.temporal.schedule_manager import (
    ensure_lifecycle_schedule,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.scheduler.temporal.workflow import LifecycleManagerWorkflow

logger = logging.getLogger(__name__)


async def run_worker(
    config: TemporalSchedulerConfig,
) -> None:
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
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[LifecycleManagerWorkflow],
        activities=[
            list_conversation_candidates,
            delete_conversation,
        ],
    )

    logger.info("[TEMPORAL] Control-plane Temporal worker running.")
    await worker.run()
