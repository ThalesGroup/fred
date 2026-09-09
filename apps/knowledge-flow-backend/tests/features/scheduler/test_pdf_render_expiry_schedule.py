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

"""Startup sync of the nightly render expiry Schedule against the configured TTL."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from temporalio.client import ScheduleOverlapPolicy

from knowledge_flow_backend.common.structures import TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler import pdf_render_expiry_schedule as module

_CONFIG = TemporalSchedulerConfig(host="temporal:7233", task_queue="ingestion", workflow_id_prefix="pipeline")


def test_a_positive_ttl_poses_a_daily_three_am_utc_schedule() -> None:
    ensure = AsyncMock(return_value="pipeline-pdf-render-expiry")
    delete = AsyncMock()
    with patch.object(module, "ensure_schedule", ensure), patch.object(module, "delete_schedule_if_exists", delete):
        schedule_id = asyncio.run(module.sync_pdf_render_expiry_schedule(MagicMock(), _CONFIG, 30))

    assert schedule_id == "pipeline-pdf-render-expiry"
    delete.assert_not_awaited()
    kwargs = ensure.await_args.kwargs
    assert ensure.await_args.args[1] == "pipeline-pdf-render-expiry"
    assert kwargs["workflow"] == "ExpirePdfRendersWorkflow"
    assert kwargs["workflow_id"] == "pipeline-pdf-render-expiry-run"
    assert kwargs["task_queue"] == "ingestion"
    (calendar,) = kwargs["spec"].calendars
    assert [(r.start, r.end) for r in calendar.hour] == [(3, 3)]
    assert [(r.start, r.end) for r in calendar.minute] == [(0, 0)]
    assert kwargs["spec"].time_zone_name == "UTC"
    assert kwargs["policy"].overlap == ScheduleOverlapPolicy.SKIP
    assert kwargs["policy"].catchup_window == timedelta(hours=1)


def test_a_zero_ttl_removes_the_schedule_instead() -> None:
    ensure = AsyncMock()
    delete = AsyncMock(return_value=True)
    client = MagicMock()
    with patch.object(module, "ensure_schedule", ensure), patch.object(module, "delete_schedule_if_exists", delete):
        schedule_id = asyncio.run(module.sync_pdf_render_expiry_schedule(client, _CONFIG, 0))

    assert schedule_id is None
    ensure.assert_not_awaited()
    delete.assert_awaited_once_with(client, "pipeline-pdf-render-expiry")
