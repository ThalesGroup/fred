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

"""Unit tests for `IngestionTaskService.start_revectorize` (MIGR-07).

A revectorize job isn't a `FileToProcess` pipeline (scope resolution happens inside
the workflow itself), so it doesn't go through `submit_documents` — this is the thin
dedicated method described in CORPUS-REVECTORIZE-RFC.md §3. Only the Temporal backend
supports it; the in-memory scheduler backend raises clearly instead of silently no-op'ing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.features.scheduler.base_scheduler import WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.temporal_scheduler import TemporalScheduler

_USER = KeycloakUser(uid="alice", username="alice", email=None, roles=[])


def _bare_service(scheduler, max_parallelism: int) -> IngestionTaskService:
    """Construct an IngestionTaskService without running __init__ (which needs a
    real SchedulerConfig/MetadataService) — only `_scheduler`/`_max_parallelism`
    matter for `start_revectorize`."""
    service = IngestionTaskService.__new__(IngestionTaskService)
    service._scheduler = scheduler
    service._max_parallelism = max_parallelism
    return service


def test_start_revectorize_delegates_to_temporal_scheduler_with_expected_payload():
    fake_scheduler = MagicMock(spec=TemporalScheduler)
    fake_scheduler.start_revectorize = AsyncMock(return_value=WorkflowHandle(workflow_id="wf-1", run_id="run-1"))
    service = _bare_service(fake_scheduler, max_parallelism=4)

    handle = asyncio.run(
        service.start_revectorize(
            user=_USER,
            scope={"source_tag": "kea-import"},
            options={"mode": "full", "force": False, "embedding_model": None},
            task_id="task-1",
        )
    )

    assert handle.workflow_id == "wf-1"
    fake_scheduler.start_revectorize.assert_awaited_once()
    _, kwargs = fake_scheduler.start_revectorize.call_args
    assert kwargs["task_id"] == "task-1"
    assert kwargs["payload"] == {
        "scope": {"source_tag": "kea-import"},
        "options": {"mode": "full", "force": False, "embedding_model": None},
        "user": _USER.model_dump(),
        "task_id": "task-1",
        "max_parallelism": 4,
    }


def test_start_revectorize_raises_when_scheduler_backend_is_not_temporal():
    service = _bare_service(MagicMock(), max_parallelism=1)  # plain mock, not a TemporalScheduler

    with pytest.raises(NotImplementedError):
        asyncio.run(service.start_revectorize(user=_USER, scope={}, options={}, task_id="task-1"))
