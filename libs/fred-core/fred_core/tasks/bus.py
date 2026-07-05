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
import logging
from typing import AsyncIterator, Awaitable, Callable, Protocol

from pydantic import TypeAdapter

from fred_core.tasks.models import TaskEvent

logger = logging.getLogger(__name__)

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)


class Subscription:
    """A live task-event subscription whose listener is attached at ``open`` —
    before any replay.

    The SSE endpoint replays persisted events and then follows live ones. If it
    subscribed *after* replaying, an event published in the gap between the replay
    snapshot and the subscription would be lost — and if that event is terminal,
    the stream hangs on heartbeats forever. Opening the subscription first buffers
    everything from that instant; the consumer drains the buffer (deduped by
    ``seq`` against the replay) and then follows live events until a terminal
    state or close.
    """

    def __init__(
        self,
        queue: asyncio.Queue[TaskEvent | None],
        detach: Callable[[], Awaitable[None]],
    ) -> None:
        self._queue = queue
        self._detach = detach
        self._closed = False

    def drain_ready(self) -> list[TaskEvent]:
        """Non-blocking: pop every event buffered so far. Used to flush the race
        window when the task is already terminal by the time replay finishes."""
        events: list[TaskEvent] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                events.append(item)
        return events

    async def __aiter__(self) -> AsyncIterator[TaskEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event
            if event.state.is_terminal:
                break

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._detach()


class IEventBus(Protocol):
    async def publish(self, event: TaskEvent) -> None: ...
    def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]: ...
    async def open_subscription(self, task_id: str) -> Subscription: ...


class MemoryEventBus:
    """
    In-process asyncio queue bus — no external services required.
    One queue per task_id. Safe for dev / memory-scheduler mode.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[TaskEvent | None]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: TaskEvent) -> None:
        async with self._lock:
            listeners = self._queues.get(event.task_id, [])
        for q in listeners:
            await q.put(event)

    async def open_subscription(self, task_id: str) -> Subscription:
        q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        async with self._lock:
            self._queues.setdefault(task_id, []).append(q)

        async def _detach() -> None:
            async with self._lock:
                listeners = self._queues.get(task_id, [])
                if q in listeners:
                    listeners.remove(q)
                if not listeners:
                    self._queues.pop(task_id, None)

        return Subscription(q, _detach)

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        sub = await self.open_subscription(task_id)
        try:
            async for event in sub:
                yield event
        finally:
            await sub.aclose()


class PostgresEventBus:
    """
    Postgres LISTEN/NOTIFY bus for multi-process / Temporal mode.
    Channel name: task:<task_id>
    Payload: TaskEvent serialised as JSON.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def publish(self, event: TaskEvent) -> None:
        import asyncpg  # type: ignore[import]

        payload = event.model_dump_json()
        channel = f"task:{event.task_id}"
        conn = await asyncpg.connect(self._dsn)
        try:
            await conn.execute("SELECT pg_notify($1, $2)", channel, payload)
        finally:
            await conn.close()

    async def open_subscription(self, task_id: str) -> Subscription:
        import asyncpg  # type: ignore[import]

        loop = asyncio.get_running_loop()
        q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        channel = f"task:{task_id}"

        def _on_notify(
            _conn: asyncpg.Connection,
            _pid: int,
            _channel: str,
            payload: str,
        ) -> None:
            try:
                event = _EVENT_ADAPTER.validate_json(payload)
                loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                logger.warning(
                    "[PostgresEventBus] Failed to parse event", exc_info=True
                )

        conn = await asyncpg.connect(self._dsn)
        await conn.add_listener(channel, _on_notify)

        async def _detach() -> None:
            try:
                await conn.remove_listener(channel, _on_notify)
            except Exception:
                logger.debug("[PostgresEventBus] remove_listener failed", exc_info=True)
            await conn.close()

        return Subscription(q, _detach)

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        sub = await self.open_subscription(task_id)
        try:
            async for event in sub:
                yield event
        finally:
            await sub.aclose()
