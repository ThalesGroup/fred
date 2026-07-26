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

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from knowledge_flow_backend.features.scheduler.temporal_scheduler import TemporalScheduler, _rpc_timeout
from knowledge_flow_backend.features.scheduler.workflow import RevectorizeCorpusWorkflow


def test_rpc_timeout_converts_seconds_to_timedelta() -> None:
    # Used to bound client.start_workflow(...) so a stuck Temporal frontend
    # fails that single call instead of hanging the upload HTTP stream forever.
    assert _rpc_timeout(10) == timedelta(seconds=10)


def test_rpc_timeout_returns_none_when_unset() -> None:
    assert _rpc_timeout(None) is None


def test_rpc_timeout_returns_none_for_zero() -> None:
    # 0 means "no deadline" here, same as None — never an instant-timeout footgun.
    assert _rpc_timeout(0) is None


def _bare_scheduler(client: MagicMock) -> TemporalScheduler:
    """Construct a TemporalScheduler without running __init__ (which needs a real
    SchedulerConfig) — only `_scheduler_config`/`_client_provider` matter here."""
    scheduler = TemporalScheduler.__new__(TemporalScheduler)
    scheduler._scheduler_config = MagicMock()
    scheduler._scheduler_config.temporal.task_queue = "ingestion"
    scheduler._scheduler_config.temporal.rpc_timeout_seconds = None
    client_provider = MagicMock()
    client_provider.get_client = AsyncMock(return_value=client)
    scheduler._client_provider = client_provider
    return scheduler


def test_start_revectorize_starts_the_workflow_on_the_ingestion_queue_with_a_task_scoped_id() -> None:
    """MIGR-07: `RevectorizeCorpusWorkflow` runs on the same task queue as the rest
    of ingestion (CORPUS-REVECTORIZE-RFC.md §3), keyed by task_id so the workflow_id
    is stable and traceable back to its task_run row."""
    fake_client = MagicMock()
    fake_workflow_handle = MagicMock(id="revectorize-task-1", first_execution_run_id="run-1")
    fake_client.start_workflow = AsyncMock(return_value=fake_workflow_handle)
    scheduler = _bare_scheduler(fake_client)

    payload = {"scope": {"source_tag": "kea-import"}, "options": {}, "user": {}, "task_id": "task-1", "max_parallelism": 1}
    handle = asyncio.run(scheduler.start_revectorize(payload=payload, task_id="task-1"))

    assert handle.workflow_id == "revectorize-task-1"
    assert handle.run_id == "run-1"
    fake_client.start_workflow.assert_awaited_once()
    args, kwargs = fake_client.start_workflow.call_args
    assert args[0] == RevectorizeCorpusWorkflow.run
    assert args[1] == payload
    assert kwargs["id"] == "revectorize-task-1"
    assert kwargs["task_queue"] == "ingestion"
