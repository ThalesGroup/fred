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
from typing import Any, AsyncIterator, Protocol

from pydantic import TypeAdapter

from fred_core.tasks.models import TaskEvent

logger = logging.getLogger(__name__)

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)


# ---------------------------------------------------------------------------
# Subscription objects — async context manager + async iterable.
# Enter the context manager to establish the channel *before* replaying from
# DB; this closes the race where a pg_notify fires between replay and LISTEN.
# ---------------------------------------------------------------------------


class _MemorySubscription:
    """Registers a queue with the in-process bus on __aenter__."""

    def __init__(
        self,
        queues: dict[str, list["asyncio.Queue[TaskEvent | None]"]],
        lock: asyncio.Lock,
        task_id: str,
    ) -> None:
        self._queues = queues
        self._lock = lock
        self._task_id = task_id
        self._q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()

    async def __aenter__(self) -> "_MemorySubscription":
        async with self._lock:
            self._queues.setdefault(self._task_id, []).append(self._q)
        return self

    async def __aexit__(self, *_: object) -> None:
        async with self._lock:
            listeners = self._queues.get(self._task_id, [])
            if self._q in listeners:
                listeners.remove(self._q)
            if not listeners:
                self._queues.pop(self._task_id, None)

    def __aiter__(self) -> "_MemorySubscription":
        return self

    async def __anext__(self) -> TaskEvent:
        event = await self._q.get()
        if event is None:
            raise StopAsyncIteration
        return event


class _PostgresSubscription:
    """Opens an asyncpg connection and calls add_listener on __aenter__."""

    def __init__(self, dsn: str, task_id: str) -> None:
        self._dsn = dsn
        self._task_id = task_id
        self._q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        self._conn: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _on_notify(
        self,
        _conn: Any,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        try:
            event = _EVENT_ADAPTER.validate_json(payload)
            assert self._loop is not None
            self._loop.call_soon_threadsafe(self._q.put_nowait, event)
        except Exception:
            logger.warning("[PostgresEventBus] Failed to parse event", exc_info=True)

    async def __aenter__(self) -> "_PostgresSubscription":
        import asyncpg  # type: ignore[import]

        self._loop = asyncio.get_running_loop()
        channel = f"task:{self._task_id}"
        self._conn = await asyncpg.connect(self._dsn)
        await self._conn.add_listener(channel, self._on_notify)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._conn is not None:
            try:
                await self._conn.remove_listener(
                    f"task:{self._task_id}", self._on_notify
                )
            except Exception:
                logger.debug("[PostgresEventBus] remove_listener failed", exc_info=True)
            await self._conn.close()
            self._conn = None

    def __aiter__(self) -> "_PostgresSubscription":
        return self

    async def __anext__(self) -> TaskEvent:
        event = await self._q.get()
        if event is None:
            raise StopAsyncIteration
        return event


# ---------------------------------------------------------------------------
# Bus protocol
# ---------------------------------------------------------------------------


class IEventBus(Protocol):
    async def publish(self, event: TaskEvent) -> None: ...
    def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]: ...
    def open_subscription(
        self, task_id: str
    ) -> Any: ...  # returns subscription ctx-mgr + async-iterable


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


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

    def open_subscription(self, task_id: str) -> _MemorySubscription:
        """Return a subscription that registers its queue on __aenter__."""
        return _MemorySubscription(self._queues, self._lock, task_id)

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        async with self.open_subscription(task_id) as sub:
            async for event in sub:
                yield event
                if event.state.is_terminal:
                    return


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

    def open_subscription(self, task_id: str) -> _PostgresSubscription:
        """Return a subscription that establishes LISTEN on __aenter__."""
        return _PostgresSubscription(self._dsn, task_id)

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        async with self.open_subscription(task_id) as sub:
            async for event in sub:
                yield event
                if event.state.is_terminal:
                    return
