from __future__ import annotations

import logging
from datetime import timedelta

from fred_core.common import TemporalSchedulerConfig
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.service import RPCError, RPCStatusCode

from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput

logger = logging.getLogger(__name__)


def _lifecycle_schedule_id(config: TemporalSchedulerConfig) -> str:
    return f"{config.workflow_id_prefix}-lifecycle-manager"


def _lifecycle_workflow_id(config: TemporalSchedulerConfig) -> str:
    return f"{config.workflow_id_prefix}-lifecycle-manager-run"


async def ensure_lifecycle_schedule(
    client: Client,
    config: TemporalSchedulerConfig,
    workflow_input: LifecycleManagerInput,
) -> str:
    schedule_id = _lifecycle_schedule_id(config)

    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            workflow="LifecycleManagerWorkflow",
            arg=workflow_input,
            id=_lifecycle_workflow_id(config),
            task_queue=config.task_queue,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(minutes=10))]
        ),
    )

    try:
        await client.create_schedule(schedule_id, schedule)
        logger.info("[TEMPORAL] Lifecycle schedule created: %s", schedule_id)
        return schedule_id
    except ScheduleAlreadyRunningError:
        logger.info("[TEMPORAL] Lifecycle schedule already exists: %s", schedule_id)
    except RPCError as exc:
        if exc.status == RPCStatusCode.ALREADY_EXISTS:
            logger.info("[TEMPORAL] Lifecycle schedule already exists: %s", schedule_id)
        else:
            logger.exception(
                "[TEMPORAL] Failed to ensure lifecycle schedule id=%s", schedule_id
            )
            raise

    # Validate that an existing schedule can be resolved.
    handle = client.get_schedule_handle(schedule_id)
    try:
        await handle.describe()
    except RPCError:
        logger.exception(
            "[TEMPORAL] Schedule exists but describe failed for id=%s", schedule_id
        )
        raise
    return schedule_id
