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

"""Worker bootstrap: housekeeping schedules must never keep ingestion from starting."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge_flow_backend.common.structures import TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler import worker as worker_module

_CONFIG = TemporalSchedulerConfig(host="temporal:7233", task_queue="ingestion", workflow_id_prefix="pipeline")


def _run_worker_with(sync_side_effect) -> tuple[AsyncMock, MagicMock]:
    client = MagicMock()
    sync = AsyncMock(side_effect=sync_side_effect)
    worker_cls = MagicMock()
    worker_cls.return_value.run = AsyncMock()
    with (
        patch.object(worker_module.Client, "connect", AsyncMock(return_value=client)),
        patch.object(worker_module, "sync_pdf_render_expiry_schedule", sync),
        patch.object(worker_module, "Worker", worker_cls),
    ):
        asyncio.run(worker_module.run_worker(_CONFIG, pdf_render_ttl_days=7))
    return sync, worker_cls


def test_schedule_sync_failure_does_not_block_the_ingestion_worker() -> None:
    sync, worker_cls = _run_worker_with(RuntimeError("temporal refused create_schedule"))

    sync.assert_awaited_once()
    worker_cls.assert_called_once()
    worker_cls.return_value.run.assert_awaited_once()


def test_schedule_sync_receives_the_configured_ttl() -> None:
    sync, _ = _run_worker_with(None)

    _, config, ttl_days = sync.await_args.args
    assert (config, ttl_days) == (_CONFIG, 7)
