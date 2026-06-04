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

from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import MigrationTaskEvent, TaskEvent, TaskState

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _event(seq: int, state: TaskState = TaskState.running) -> MigrationTaskEvent:
    return MigrationTaskEvent(
        task_id="task-1",
        state=state,
        seq=seq,
        timestamp=_NOW,
    )


@pytest.mark.asyncio
async def test_memory_bus_subscriber_receives_published_events() -> None:
    bus = MemoryEventBus()
    received: list[TaskEvent] = []

    async def consumer() -> None:
        async for ev in bus.subscribe("task-1"):
            received.append(ev)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let subscriber register

    await bus.publish(_event(1))
    await bus.publish(_event(2))
    await bus.publish(_event(3, TaskState.succeeded))

    await task
    assert len(received) == 3
    assert received[0].seq == 1
    assert received[2].state == TaskState.succeeded


@pytest.mark.asyncio
async def test_memory_bus_terminal_state_closes_stream() -> None:
    bus = MemoryEventBus()
    received: list[TaskEvent] = []

    async def consumer() -> None:
        async for ev in bus.subscribe("task-1"):
            received.append(ev)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    await bus.publish(_event(1, TaskState.failed))
    await task

    assert len(received) == 1
    assert received[0].state.is_terminal


@pytest.mark.asyncio
async def test_memory_bus_multiple_subscribers_each_receive_all_events() -> None:
    bus = MemoryEventBus()
    a: list[TaskEvent] = []
    b: list[TaskEvent] = []

    async def consume(dest: list[TaskEvent]) -> None:
        async for ev in bus.subscribe("task-1"):
            dest.append(ev)

    t1 = asyncio.create_task(consume(a))
    t2 = asyncio.create_task(consume(b))
    await asyncio.sleep(0)

    await bus.publish(_event(1))
    await bus.publish(_event(2, TaskState.succeeded))

    await asyncio.gather(t1, t2)
    assert len(a) == len(b) == 2


@pytest.mark.asyncio
async def test_memory_bus_no_events_for_different_task_id() -> None:
    bus = MemoryEventBus()
    received: list[TaskEvent] = []

    async def consumer() -> None:
        async for ev in bus.subscribe("task-other"):
            received.append(ev)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    # Publish to a different task_id
    await bus.publish(_event(1))  # task-1, not task-other
    # Terminate task-other so the consumer exits
    other_event = MigrationTaskEvent(
        task_id="task-other", state=TaskState.cancelled, seq=1, timestamp=_NOW
    )
    await bus.publish(other_event)
    await task

    assert received == [other_event]
