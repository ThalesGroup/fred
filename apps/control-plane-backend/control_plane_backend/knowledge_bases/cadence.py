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

"""An instance's schedule, projected onto the workflow engine.

Fred owns recurrence because a pod that scheduled itself would have to stay up
between runs, and the schedule starts exactly the workflow, on exactly the
queue, that a manual trigger starts — so the two cannot drift apart.
"""

from __future__ import annotations

from fred_core.common import TemporalSchedulerConfig
from fred_core.scheduler import (
    Schedule,
    delete_schedule_if_exists,
    ensure_schedule,
    to_temporal_spec,
)
from fred_sdk.knowledge_base.routing import (
    SYNCHRONIZE_WORKFLOW,
    SynchronizeInput,
    task_queue_for,
)
from temporalio.client import Client, ScheduleState


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
    schedule: Schedule,
    suspended: bool,
    max_attempts: int,
) -> str:
    """Create this instance's schedule, or align an existing one with it.

    Idempotent so that retrying a failed folder creation converges instead of
    colliding: an id that already exists is updated rather than refused.
    """
    identifier = schedule_id(config, instance_id)
    return await ensure_schedule(
        client,
        identifier,
        workflow=SYNCHRONIZE_WORKFLOW,
        workflow_id=identifier,
        task_queue=task_queue_for(definition_id),
        # Spread over the instance id: an interval is anchored on the epoch,
        # so without it every instance of one period fires on the same second.
        spec=to_temporal_spec(schedule, spread_over=instance_id),
        # Identifiers and the attempt budget, never a configuration value: the
        # engine keeps a workflow's input for as long as its retention policy
        # says, so only what is safe to keep for ever goes in. The pod fetches
        # the rest per run, against the identity it authenticates with.
        args=[
            SynchronizeInput(
                definition_id=definition_id,
                instance_id=instance_id,
                team_id=team_id,
                max_attempts=max_attempts,
            )
        ],
        state=ScheduleState(paused=suspended),
    )


async def drop_cadence(
    client: Client, config: TemporalSchedulerConfig, *, instance_id: str
) -> None:
    """Remove this instance's schedule. A schedule already gone is not an error."""
    await delete_schedule_if_exists(client, schedule_id(config, instance_id))
