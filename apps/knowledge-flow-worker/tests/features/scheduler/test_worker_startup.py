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
import json
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.api.common.v1 import Payload
from temporalio.contrib.pydantic import pydantic_data_converter

from knowledge_flow_worker.common.structures import IngestionWorkerRole, SchedulerConfig, TemporalSchedulerConfig
from knowledge_flow_worker.features.scheduler import worker as worker_module
from knowledge_flow_worker.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition

_CONFIG = TemporalSchedulerConfig(host="temporal:7233", task_queue="ingestion", workflow_id_prefix="pipeline")


def _run_worker_with(*, roles: list[IngestionWorkerRole] | None = None, connect: AsyncMock | None = None, **kwargs) -> tuple[AsyncMock, MagicMock]:
    client = MagicMock()
    cleanup = AsyncMock()
    worker_cls = MagicMock()
    worker_cls.return_value.run = AsyncMock()
    with (
        patch.object(worker_module.Client, "connect", connect or AsyncMock(return_value=client)),
        patch.object(worker_module, "manager_cleanup", cleanup),
        patch.object(worker_module, "Worker", worker_cls),
    ):
        asyncio.run(worker_module.run_worker(_CONFIG, roles=roles, **kwargs))
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


# ── payload conversion ────────────────────────────────────────────────────────


def test_the_worker_converts_payloads_with_pydantic() -> None:
    connect = AsyncMock(return_value=MagicMock())
    _run_worker_with(roles=[IngestionWorkerRole.common], connect=connect)
    assert connect.await_args.kwargs["data_converter"] is pydantic_data_converter


def test_control_plane_submissions_and_activity_models_round_trip_through_the_converter() -> None:
    """The Control Plane encodes a submission as `json/plain` serde JSON; the worker
    decodes it and exchanges its files between workflow and activities as models."""
    fixture = Path(__file__).resolve().parents[4] / "control-plane/tests/fixtures/processing/submissions.json"
    converter = pydantic_data_converter.payload_converter
    for submitted in json.loads(fixture.read_text()):
        payload = Payload(metadata={"encoding": b"json/plain"}, data=json.dumps(submitted).encode())
        [definition] = converter.from_payloads([payload], [PipelineDefinition])
        assert definition == PipelineDefinition.model_validate(submitted)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            encoded = converter.to_payloads([definition.files[0]])
        assert converter.from_payloads(encoded, [FileToProcess]) == [definition.files[0]]
