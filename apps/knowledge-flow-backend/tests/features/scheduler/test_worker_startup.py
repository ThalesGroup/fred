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

"""Worker bootstrap: what each role registers, on which queue, and who owns the
manager cleanup loop."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_flow_backend.common.structures import IngestionWorkerRole, SchedulerConfig, TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler import worker as worker_module

_CONFIG = TemporalSchedulerConfig(host="temporal:7233", task_queue="ingestion", workflow_id_prefix="pipeline")


def _run_worker_with(*, roles: list[IngestionWorkerRole] | None = None, **kwargs) -> tuple[AsyncMock, MagicMock]:
    client = MagicMock()
    cleanup = AsyncMock()
    worker_cls = MagicMock()
    worker_cls.return_value.run = AsyncMock()
    with (
        patch.object(worker_module.Client, "connect", AsyncMock(return_value=client)),
        patch("knowledge_flow_backend.features.manager_processing.cleanup.run", cleanup),
        patch.object(worker_module, "Worker", worker_cls),
    ):
        asyncio.run(worker_module.run_worker(_CONFIG, roles=roles, manager_processing=True, **kwargs))
    return cleanup, worker_cls


def _worker_kwargs_by_queue(worker_cls: MagicMock) -> dict[str, dict]:
    return {call.kwargs["task_queue"]: call.kwargs for call in worker_cls.call_args_list}


# ── what each role registers ──────────────────────────────────────────────────


def test_the_common_role_polls_the_base_queue_with_every_workflow() -> None:
    _, worker_cls = _run_worker_with(roles=[IngestionWorkerRole.common])

    kwargs = _worker_kwargs_by_queue(worker_cls)["ingestion"]
    assert kwargs["workflows"] == [
        worker_module.ProcessPush,
        worker_module.ProcessPushFile,
        worker_module.GetPushFileMetadata,
        worker_module.PushInputProcess,
        worker_module.OutputProcess,
        worker_module.SetDocumentRetrievable,
    ]
    assert kwargs["activities"] == [
        worker_module.get_push_file_metadata,
        worker_module.output_process,
        worker_module.set_document_retrievable,
        worker_module.record_retrievable_applied,
        worker_module.confirm_document_retrievable,
    ]


def test_the_common_role_does_not_run_extraction() -> None:
    """Extraction is what this split moves away; leaving it registered here would
    let the common pods pick it up again the moment a queue name drifted."""
    _, worker_cls = _run_worker_with(roles=[IngestionWorkerRole.common])

    registered = _worker_kwargs_by_queue(worker_cls)["ingestion"]["activities"]
    assert worker_module.push_input_process not in registered


@pytest.mark.parametrize(
    ("role", "expected_queue"),
    [
        (IngestionWorkerRole.extraction_fast, "ingestion-fast"),
        (IngestionWorkerRole.extraction_medium, "ingestion-medium"),
        (IngestionWorkerRole.extraction_rich, "ingestion-rich"),
    ],
)
def test_an_extraction_role_runs_only_manager_push_extraction(role, expected_queue) -> None:
    _, worker_cls = _run_worker_with(roles=[role])

    kwargs = _worker_kwargs_by_queue(worker_cls)[expected_queue]
    assert kwargs["workflows"] == []
    assert set(kwargs["activities"]) == {worker_module.push_input_process}


def test_a_multi_role_process_serves_every_queue() -> None:
    """A developer runs one process; the chart runs one role per deployment. Both
    have to add up to a consumer on all four queues."""
    _, worker_cls = _run_worker_with(roles=list(IngestionWorkerRole))

    assert set(_worker_kwargs_by_queue(worker_cls)) == {"ingestion", "ingestion-fast", "ingestion-medium", "ingestion-rich"}
    assert worker_cls.return_value.run.await_count == 4


# ── concurrency ───────────────────────────────────────────────────────────────


def test_activity_concurrency_is_applied_per_role() -> None:
    """One extraction per rich pod is the whole point of the rich deployment."""
    _, worker_cls = _run_worker_with(roles=[IngestionWorkerRole.extraction_rich], max_concurrent_activities=1)

    assert _worker_kwargs_by_queue(worker_cls)["ingestion-rich"]["max_concurrent_activities"] == 1


# Manager maintenance runs only alongside the common worker.


def test_the_common_worker_runs_manager_cleanup() -> None:
    cleanup, worker_cls = _run_worker_with(roles=[IngestionWorkerRole.common])
    cleanup.assert_awaited_once_with()
    worker_cls.return_value.run.assert_awaited_once()


def test_an_extraction_only_worker_leaves_cleanup_to_the_common_worker() -> None:
    cleanup, worker_cls = _run_worker_with(roles=[IngestionWorkerRole.extraction_rich])
    cleanup.assert_not_awaited()
    worker_cls.return_value.run.assert_awaited_once()


# ── configuration ─────────────────────────────────────────────────────────────


def test_worker_roles_default_to_serving_every_queue() -> None:
    """A config that says nothing about roles must still consume everything it
    routes, rather than parking extraction on a queue nobody polls."""
    config = SchedulerConfig(temporal=_CONFIG)

    assert config.worker_roles == list(IngestionWorkerRole)


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        ([], "at least one role"),
        (["common", "common"], "must not repeat"),
    ],
)
def test_an_unusable_role_list_is_refused(roles, message) -> None:
    with pytest.raises(ValueError, match=message):
        SchedulerConfig(temporal=_CONFIG, worker_roles=roles)
