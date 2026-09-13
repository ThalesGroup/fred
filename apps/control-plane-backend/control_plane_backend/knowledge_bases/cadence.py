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
An instance's cadence, projected onto the workflow engine.

Fred owns recurrence because a pod that scheduled itself would have to stay up
between runs, which contradicts a pod that only dials out. So a cadence costs
the author nothing and costs Fred one schedule per instance.

The schedule starts exactly the workflow a manual trigger starts, on the queue
derived from the definition's own name — one dispatch path, so a scheduled run
and a triggered one cannot drift apart.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fred_core.common import TemporalSchedulerConfig
from fred_sdk.knowledge_base.schedule import RunCadence
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode

from control_plane_backend.knowledge_bases.dispatch import (
    SYNCHRONIZE_WORKFLOW,
    run_input,
    task_queue_for_definition,
)

logger = logging.getLogger(__name__)

_EVERY: dict[RunCadence, timedelta] = {
    RunCadence.hourly: timedelta(hours=1),
    RunCadence.daily: timedelta(days=1),
    RunCadence.weekly: timedelta(days=7),
}


def schedule_id(config: TemporalSchedulerConfig, instance_id: str) -> str:
    """One schedule per instance, named after it so deletion needs no lookup."""
    return f"{config.workflow_id_prefix}-kb-{instance_id}"


async def register_cadence(
    client: Client,
    config: TemporalSchedulerConfig,
    *,
    instance_id: str,
    definition_id: str,
    team_id: str,
    cadence: RunCadence,
    suspended: bool,
    max_attempts: int,
) -> str:
    """Create this instance's schedule, or align an existing one with it.

    Idempotent so that retrying a failed folder creation converges instead of
    colliding: an id that already exists is updated rather than refused.
    """
    identifier = schedule_id(config, instance_id)
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            SYNCHRONIZE_WORKFLOW,
            run_input(
                definition_id=definition_id,
                instance_id=instance_id,
                team_id=team_id,
                max_attempts=max_attempts,
            ),
            id=identifier,
            task_queue=task_queue_for_definition(definition_id),
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=_EVERY[cadence])]),
        state=ScheduleState(paused=suspended),
    )
    try:
        await client.create_schedule(identifier, schedule)
        return identifier
    except (ScheduleAlreadyRunningError, RPCError) as exc:
        if isinstance(exc, RPCError) and exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise
    await update_cadence(
        client,
        config,
        instance_id=instance_id,
        definition_id=definition_id,
        team_id=team_id,
        cadence=cadence,
        suspended=suspended,
        max_attempts=max_attempts,
    )
    return identifier


async def update_cadence(
    client: Client,
    config: TemporalSchedulerConfig,
    *,
    instance_id: str,
    definition_id: str,
    team_id: str,
    cadence: RunCadence,
    suspended: bool,
    max_attempts: int,
) -> None:
    """Point an existing schedule at a new cadence, or pause it.

    An update replaces what the schedule will start next; a run already in
    flight is a workflow execution of its own and is never touched by this.
    """
    handle = client.get_schedule_handle(schedule_id(config, instance_id))

    async def _replace(_: ScheduleUpdateInput) -> ScheduleUpdate:
        return ScheduleUpdate(
            schedule=Schedule(
                action=ScheduleActionStartWorkflow(
                    SYNCHRONIZE_WORKFLOW,
                    run_input(
                        definition_id=definition_id,
                        instance_id=instance_id,
                        team_id=team_id,
                        max_attempts=max_attempts,
                    ),
                    id=schedule_id(config, instance_id),
                    task_queue=task_queue_for_definition(definition_id),
                ),
                spec=ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=_EVERY[cadence])]
                ),
                state=ScheduleState(paused=suspended),
            )
        )

    await handle.update(_replace)


async def drop_cadence(
    client: Client, config: TemporalSchedulerConfig, *, instance_id: str
) -> None:
    """Remove this instance's schedule. A schedule already gone is not an error."""
    handle = client.get_schedule_handle(schedule_id(config, instance_id))
    try:
        await handle.delete()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        logger.info(
            "[knowledge-base] schedule for instance %s was already gone", instance_id
        )
