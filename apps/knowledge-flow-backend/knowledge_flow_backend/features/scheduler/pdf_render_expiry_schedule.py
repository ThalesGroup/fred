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

"""Nightly Schedule for the PDF render expiry, synced from configuration at worker start."""

from __future__ import annotations

import logging
from datetime import timedelta

from fred_core.scheduler.schedules import delete_schedule_if_exists, ensure_schedule
from temporalio.client import (
    Client,
    ScheduleCalendarSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
)

from knowledge_flow_backend.common.structures import TemporalSchedulerConfig

logger = logging.getLogger(__name__)

EXPIRY_HOUR_UTC = 3


def pdf_render_expiry_schedule_id(config: TemporalSchedulerConfig) -> str:
    return f"{config.workflow_id_prefix}-pdf-render-expiry"


async def sync_pdf_render_expiry_schedule(client: Client, config: TemporalSchedulerConfig, ttl_days: int) -> str | None:
    """Pose the nightly Schedule when a TTL is set, remove it when the TTL is 0.

    The TTL itself is not stored in the Schedule: the activity reads it from
    configuration on every run, so changing it never requires recreating this.
    """
    schedule_id = pdf_render_expiry_schedule_id(config)
    if ttl_days <= 0:
        removed = await delete_schedule_if_exists(client, schedule_id)
        logger.info("[SCHEDULER] PDF render expiry disabled (ttl_days=%d); schedule %s", ttl_days, "removed" if removed else "absent")
        return None

    await ensure_schedule(
        client,
        schedule_id,
        workflow="ExpirePdfRendersWorkflow",
        workflow_id=f"{schedule_id}-run",
        task_queue=config.task_queue,
        spec=ScheduleSpec(
            calendars=[ScheduleCalendarSpec(hour=(ScheduleRange(EXPIRY_HOUR_UTC),), minute=(ScheduleRange(0),))],
            time_zone_name="UTC",
        ),
        # One pass per night is enough: never stack runs, and after a long worker
        # outage run once now rather than replaying every missed night.
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=timedelta(hours=1)),
    )
    logger.info("[SCHEDULER] PDF render expiry schedule ready: %s (daily %02d:00 UTC, ttl_days=%d)", schedule_id, EXPIRY_HOUR_UTC, ttl_days)
    return schedule_id
