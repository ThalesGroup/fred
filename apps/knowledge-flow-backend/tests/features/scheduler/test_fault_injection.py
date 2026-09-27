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

"""Fault selection and effects, with all waiting and process exits replaced."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.exceptions import ApplicationError

from knowledge_flow_backend.features.scheduler import fault_injection as faults


@pytest.fixture
def harness(monkeypatch):
    for suffix in ("", "_STAGE", "_FILE", "_DELAY_SECONDS", "_ATTEMPTS"):
        monkeypatch.delenv(f"FRED_INGESTION_FAULT{suffix}", raising=False)
    info = SimpleNamespace(activity_type="push_input_process", attempt=1)
    logger = Mock()
    sleep = AsyncMock()
    waits = []

    async def heartbeat_wait(awaitable, **kwargs):
        waits.append(kwargs)
        await awaitable

    exit_worker = Mock(side_effect=SystemExit(86))
    monkeypatch.setattr(faults.activity, "in_activity", lambda: True)
    monkeypatch.setattr(faults.activity, "info", lambda: info)
    monkeypatch.setattr(faults.activity, "logger", logger)
    monkeypatch.setattr(faults, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(faults, "await_with_heartbeat", heartbeat_wait)
    monkeypatch.setattr(faults.os, "_exit", exit_worker)

    def arm(mode="activity_error", stage="extraction", attempts="1"):
        monkeypatch.setenv("FRED_INGESTION_FAULT", mode)
        monkeypatch.setenv("FRED_INGESTION_FAULT_STAGE", stage)
        monkeypatch.setenv("FRED_INGESTION_FAULT_FILE", "demo.pdf")
        monkeypatch.setenv("FRED_INGESTION_FAULT_DELAY_SECONDS", "180")
        monkeypatch.setenv("FRED_INGESTION_FAULT_ATTEMPTS", attempts)

    return SimpleNamespace(info=info, arm=arm, sleep=sleep, waits=waits, exit=exit_worker)


async def inject(stage="extraction", filename="demo.pdf"):
    await faults.inject_ingestion_fault(stage=stage, document_name=filename, document_uid="doc-1")


@pytest.mark.asyncio
async def test_disabled_hook_has_no_effect(harness):
    await inject()
    harness.sleep.assert_not_called()
    harness.exit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,permanent", [("activity_error", False), ("non_retryable_error", True)])
@pytest.mark.parametrize("activity_type", ["push_input_process", "pull_input_process"])
async def test_selected_fault_waits_with_heartbeats_then_fails(harness, mode, permanent, activity_type):
    harness.arm(mode)
    harness.info.activity_type = activity_type
    with pytest.raises(ApplicationError, match="Simulated ingestion fault") as raised:
        await inject()
    assert raised.value.type == "SimulatedIngestionFailure"
    assert raised.value.non_retryable is permanent
    harness.sleep.assert_awaited_once_with(180)
    assert harness.waits[0]["heartbeat_details"]["document_uid"] == "doc-1"
    harness.exit.assert_not_called()


@pytest.mark.asyncio
async def test_other_file_stage_and_attempt_are_untouched(harness):
    harness.arm()
    await inject(filename="other.pdf")
    await inject(stage="indexing")
    harness.info.attempt = 2
    await inject()
    harness.sleep.assert_not_called()
    harness.exit.assert_not_called()


@pytest.mark.asyncio
async def test_direct_api_call_is_never_affected(harness, monkeypatch):
    harness.arm("worker_crash")
    monkeypatch.setattr(faults.activity, "in_activity", lambda: False)
    await inject()
    harness.exit.assert_not_called()
    harness.sleep.assert_not_called()


@pytest.mark.asyncio
async def test_indexing_hook_excludes_trusted_maintenance(harness):
    harness.arm(stage="indexing")
    harness.info.activity_type = "output_process_trusted"
    await inject(stage="indexing")
    harness.sleep.assert_not_called()
    harness.info.activity_type = "output_process"
    with pytest.raises(ApplicationError):
        await inject(stage="indexing")


@pytest.mark.asyncio
async def test_worker_crash_uses_abrupt_process_exit(harness):
    harness.arm("worker_crash")
    with pytest.raises(SystemExit) as raised:
        await inject()
    assert raised.value.code == 86
    harness.exit.assert_called_once_with(86)
    harness.sleep.assert_awaited_once_with(180)


@pytest.mark.asyncio
async def test_delay_returns_without_faking_a_temporal_timeout(harness):
    harness.arm("delay", attempts="all")
    harness.info.attempt = 9
    await inject()
    harness.sleep.assert_awaited_once_with(180)
    harness.exit.assert_not_called()


@pytest.mark.asyncio
async def test_selected_attempts_do_not_use_a_process_local_counter(harness):
    harness.arm(attempts="1,3")
    for attempt in (1, 3):
        harness.info.attempt = attempt
        with pytest.raises(ApplicationError):
            await inject()
    harness.info.attempt = 4
    await inject()
    assert harness.sleep.await_count == 2


@pytest.mark.parametrize(
    "suffix,value",
    [
        ("", "typo"),
        ("_STAGE", "unknown"),
        ("_FILE", ""),
        ("_FILE", "/tmp/demo.pdf"),
        ("_DELAY_SECONDS", "-1"),
        ("_DELAY_SECONDS", "nan"),
        ("_DELAY_SECONDS", "inf"),
        ("_ATTEMPTS", "0"),
        ("_ATTEMPTS", "-1"),
        ("_ATTEMPTS", "1,no"),
    ],
)
def test_invalid_configuration_fails_before_worker_start(harness, monkeypatch, suffix, value):
    harness.arm()
    monkeypatch.setenv(f"FRED_INGESTION_FAULT{suffix}", value)
    with pytest.raises(ValueError, match="FRED_INGESTION_FAULT"):
        faults.read_ingestion_fault()
