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

"""The SSE stream must not lose an event published in the gap between the replay
snapshot and going live — especially the terminal one, whose loss would hang the
stream on heartbeats. Regression test for that replay→subscribe race."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, cast

import pytest

from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import IngestionTaskEvent, TaskState
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import task_event_stream

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _event(seq: int, state: TaskState = TaskState.running) -> IngestionTaskEvent:
    return IngestionTaskEvent(task_id="task-1", state=state, seq=seq, timestamp=_NOW)


class _FakeService:
    """Minimal TaskService surface used by task_event_stream, with a hook that
    fires *during* replay to simulate an event landing in the race window."""

    def __init__(
        self,
        bus: MemoryEventBus,
        *,
        replay_events: list[IngestionTaskEvent],
        run_state: TaskState,
        on_replay: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.bus = bus
        self._replay_events = replay_events
        self._run_state = run_state
        self._on_replay = on_replay

    async def reconcile_task(self, task_id: str) -> None:
        return None

    async def replay(self, task_id: str, *, after_seq: int) -> list[IngestionTaskEvent]:
        if self._on_replay is not None:
            await self._on_replay()
        return [e for e in self._replay_events if e.seq > after_seq]

    async def get_run(self, task_id: str) -> Any:
        return SimpleNamespace(state=self._run_state.value)


async def _never_disconnected() -> bool:
    return False


@pytest.mark.asyncio
async def test_terminal_event_raced_during_replay_is_still_delivered() -> None:
    # The task goes terminal in the window after the subscription is opened but
    # before/while replay runs: the terminal event is published to the bus and the
    # run reads back terminal. The old code (subscribe-after-replay + early return
    # on a terminal run) dropped it; the stream must now still emit it.
    bus = MemoryEventBus()
    terminal = _event(2, TaskState.succeeded)

    async def publish_terminal_during_replay() -> None:
        await bus.publish(terminal)

    service = _FakeService(
        bus,
        replay_events=[_event(1, TaskState.running)],
        run_state=TaskState.succeeded,
        on_replay=publish_terminal_during_replay,
    )

    frames = [
        frame
        async for frame in task_event_stream(
            cast(TaskService, service),
            "task-1",
            after_seq=-1,
            is_disconnected=_never_disconnected,
        )
    ]
    body = "".join(frames)

    assert "id: 1" in body  # replayed running frame
    assert "id: 2" in body and "succeeded" in body  # raced terminal, not lost


@pytest.mark.asyncio
async def test_live_events_are_deduped_against_replay_by_seq() -> None:
    # An event present in BOTH the replay and the live buffer (published in the
    # window) must be emitted exactly once.
    bus = MemoryEventBus()
    duped = _event(1, TaskState.running)
    terminal = _event(2, TaskState.succeeded)

    async def publish_dupe_and_terminal() -> None:
        await bus.publish(duped)  # same seq as a replayed event
        await bus.publish(terminal)

    service = _FakeService(
        bus,
        replay_events=[duped],
        run_state=TaskState.running,  # not terminal → follow the live stream
        on_replay=publish_dupe_and_terminal,
    )

    frames = [
        frame
        async for frame in task_event_stream(
            cast(TaskService, service),
            "task-1",
            after_seq=-1,
            is_disconnected=_never_disconnected,
        )
    ]
    body = "".join(frames)

    assert body.count("id: 1") == 1  # deduped
    assert "id: 2" in body  # terminal still delivered


@pytest.mark.asyncio
async def test_idle_stream_recovers_terminal_event_without_notification(monkeypatch):
    import fred_core.tasks.sse as sse

    monkeypatch.setattr(sse, "HEARTBEAT_INTERVAL", 0.001)
    bus = MemoryEventBus()
    service = _FakeService(bus, replay_events=[_event(1)], run_state=TaskState.running)
    stream = task_event_stream(
        cast(TaskService, service),
        "task-1",
        after_seq=0,
        is_disconnected=_never_disconnected,
    )
    assert "id: 1" in await anext(stream)
    service._replay_events.append(_event(2, TaskState.failed))
    frame = await asyncio.wait_for(anext(stream), timeout=1)
    assert "id: 2" in frame and '"failed"' in frame
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert not bus._queues


@pytest.mark.asyncio
async def test_terminal_commit_after_replay_is_recovered_without_notification():
    bus = MemoryEventBus()
    service = _FakeService(bus, replay_events=[_event(1)], run_state=TaskState.running)

    async def terminal_run(task_id):
        service._replay_events.append(_event(2, TaskState.succeeded))
        return SimpleNamespace(state=TaskState.succeeded)

    service.get_run = terminal_run
    frames = [
        frame
        async for frame in task_event_stream(
            cast(TaskService, service),
            "task-1",
            after_seq=0,
            is_disconnected=_never_disconnected,
        )
    ]
    assert len(frames) == 2
    assert '"succeeded"' in frames[-1]


@pytest.mark.asyncio
async def test_heartbeat_wrapper_closes_source_when_client_stops_after_a_frame():
    from fred_core.tasks.sse import with_heartbeat

    closed = False

    async def source():
        nonlocal closed
        try:
            yield "data: running\n\n"
            await asyncio.Event().wait()
        finally:
            closed = True

    stream = with_heartbeat(source())
    await anext(stream)
    await stream.aclose()
    assert closed
