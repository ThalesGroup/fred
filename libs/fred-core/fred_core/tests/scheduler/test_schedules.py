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

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fred_core.scheduler.schedules import delete_schedule_if_exists, ensure_schedule
from temporalio.client import (
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.service import RPCError, RPCStatusCode

_SPEC = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=10))])


def _client(create_side_effect=None, delete_side_effect=None) -> MagicMock:
    client = MagicMock()
    client.create_schedule = AsyncMock(side_effect=create_side_effect)
    handle = MagicMock()
    handle.update = AsyncMock()
    handle.delete = AsyncMock(side_effect=delete_side_effect)
    client.get_schedule_handle = MagicMock(return_value=handle)
    return client


def _rpc_error(status: RPCStatusCode) -> RPCError:
    return RPCError("boom", status, b"")


async def _ensure(client) -> str:
    return await ensure_schedule(
        client,
        "sched-1",
        workflow="SomeWorkflow",
        workflow_id="sched-1-run",
        task_queue="queue",
        spec=_SPEC,
    )


@pytest.mark.asyncio
async def test_ensure_schedule_creates_without_touching_the_handle() -> None:
    client = _client()

    assert await _ensure(client) == "sched-1"

    schedule_id, schedule = client.create_schedule.await_args.args
    assert schedule_id == "sched-1"
    assert schedule.action.workflow == "SomeWorkflow"
    assert schedule.action.args == []
    assert schedule.action.id == "sched-1-run"
    assert schedule.action.task_queue == "queue"
    client.get_schedule_handle.return_value.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_schedule_forwards_workflow_args() -> None:
    client = _client()

    await ensure_schedule(
        client,
        "sched-1",
        workflow="SomeWorkflow",
        workflow_id="sched-1-run",
        task_queue="queue",
        spec=_SPEC,
        args=[{"dry_run": True}],
    )

    _, schedule = client.create_schedule.await_args.args
    assert schedule.action.args == [{"dry_run": True}]


@pytest.mark.parametrize(
    "already_exists",
    [ScheduleAlreadyRunningError(), _rpc_error(RPCStatusCode.ALREADY_EXISTS)],
    ids=["sdk-error", "rpc-already-exists"],
)
@pytest.mark.asyncio
async def test_ensure_schedule_refreshes_an_existing_schedule(already_exists) -> None:
    client = _client(create_side_effect=already_exists)

    assert await _ensure(client) == "sched-1"

    handle = client.get_schedule_handle.return_value
    handle.update.assert_awaited_once()
    (updater,) = handle.update.await_args.args
    refreshed = updater(MagicMock()).schedule
    assert refreshed.action.workflow == "SomeWorkflow"
    assert refreshed.action.task_queue == "queue"
    assert refreshed.spec == _SPEC


@pytest.mark.asyncio
async def test_ensure_schedule_raises_other_rpc_errors() -> None:
    client = _client(create_side_effect=_rpc_error(RPCStatusCode.UNAVAILABLE))

    with pytest.raises(RPCError):
        await _ensure(client)
    client.get_schedule_handle.return_value.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_schedule_if_exists_reports_whether_it_deleted() -> None:
    assert await delete_schedule_if_exists(_client(), "sched-1") is True
    assert (
        await delete_schedule_if_exists(
            _client(delete_side_effect=_rpc_error(RPCStatusCode.NOT_FOUND)), "sched-1"
        )
        is False
    )


@pytest.mark.asyncio
async def test_delete_schedule_if_exists_raises_other_rpc_errors() -> None:
    with pytest.raises(RPCError):
        await delete_schedule_if_exists(
            _client(delete_side_effect=_rpc_error(RPCStatusCode.UNAVAILABLE)), "sched-1"
        )
