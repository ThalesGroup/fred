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

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import (
    ActivityContext,
    MigrationTaskEvent,
    TaskEvent,
    TaskState,
)
from fred_core.tasks.scheduler import MemoryScheduler

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


class _Params(BaseModel):
    value: str


async def _simple_activity(ctx: ActivityContext, params: _Params) -> None:
    event = MigrationTaskEvent(
        task_id=ctx.task_id,
        state=TaskState.succeeded,
        seq=1,
        timestamp=_NOW,
    )
    await ctx.emit(event)


async def _long_activity(ctx: ActivityContext, params: _Params) -> None:
    await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_memory_scheduler_runs_activity_to_completion() -> None:
    bus = MemoryEventBus()
    scheduler = MemoryScheduler()
    received: list[TaskEvent] = []

    async def collect() -> None:
        async for ev in bus.subscribe("t1"):
            received.append(ev)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await scheduler.submit("t1", _simple_activity, _Params(value="x"), bus)
    await asyncio.sleep(0.05)  # let activity run

    await collector
    assert len(received) == 1
    assert received[0].state == TaskState.succeeded


@pytest.mark.asyncio
async def test_memory_scheduler_cancel_stops_running_activity() -> None:
    bus = MemoryEventBus()
    scheduler = MemoryScheduler()

    await scheduler.submit("t2", _long_activity, _Params(value="x"), bus)
    await asyncio.sleep(0)

    assert "t2" in scheduler._tasks
    await scheduler.cancel("t2")
    await asyncio.sleep(0.05)

    task = scheduler._tasks.get("t2")
    assert task is None or task.done()


@pytest.mark.asyncio
async def test_memory_scheduler_heartbeat_is_callable() -> None:
    bus = MemoryEventBus()
    scheduler = MemoryScheduler()
    heartbeats: list[bool] = []

    async def _hb_activity(ctx: ActivityContext, params: _Params) -> None:
        ctx.heartbeat()
        heartbeats.append(True)
        event = MigrationTaskEvent(
            task_id=ctx.task_id, state=TaskState.succeeded, seq=1, timestamp=_NOW
        )
        await ctx.emit(event)

    async def collect() -> None:
        async for _ in bus.subscribe("t3"):
            pass

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await scheduler.submit("t3", _hb_activity, _Params(value="x"), bus)
    await asyncio.sleep(0.05)
    await collector

    assert heartbeats == [True]
