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

"""Idempotent Temporal Schedule bootstrap, shared by the backend workers.

A worker calls `ensure_schedule` at startup so the recurring job exists whether
this is the first boot or the hundredth; `delete_schedule_if_exists` is the
matching way to switch a recurring job off from configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.service import RPCError, RPCStatusCode

logger = logging.getLogger(__name__)


async def ensure_schedule(
    client: Client,
    schedule_id: str,
    *,
    workflow: str,
    workflow_id: str,
    task_queue: str,
    spec: ScheduleSpec,
    args: Sequence[Any] = (),
    policy: SchedulePolicy | None = None,
) -> str:
    """Create the Schedule, or bring an existing one in line with `spec`/`policy`.

    Updating on the already-exists path is what lets a task-queue or calendar
    change in configuration take effect on a deployment that already has it.
    """
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            workflow,
            args=list(args),
            id=workflow_id,
            task_queue=task_queue,
        ),
        spec=spec,
        policy=policy or SchedulePolicy(),
    )
    try:
        await client.create_schedule(schedule_id, schedule)
        logger.info("[TEMPORAL] Schedule created: %s", schedule_id)
        return schedule_id
    except ScheduleAlreadyRunningError:
        pass
    except RPCError as exc:
        if exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise

    await client.get_schedule_handle(schedule_id).update(
        lambda _current: ScheduleUpdate(schedule=schedule)
    )
    logger.info(
        "[TEMPORAL] Schedule already existed, definition refreshed: %s", schedule_id
    )
    return schedule_id


async def delete_schedule_if_exists(client: Client, schedule_id: str) -> bool:
    """Delete the Schedule; return False when there was none to delete."""
    try:
        await client.get_schedule_handle(schedule_id).delete()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    logger.info("[TEMPORAL] Schedule deleted: %s", schedule_id)
    return True
