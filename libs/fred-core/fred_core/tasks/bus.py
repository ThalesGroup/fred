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
from typing import AsyncIterator, Protocol

from pydantic import TypeAdapter

from fred_core.tasks.models import TaskEvent

logger = logging.getLogger(__name__)

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)


class IEventBus(Protocol):
    async def publish(self, event: TaskEvent) -> None: ...
    def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]: ...


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

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        q: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        async with self._lock:
            self._queues.setdefault(task_id, []).append(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                yield event
                if event.state.is_terminal:
                    break
        finally:
            async with self._lock:
                listeners = self._queues.get(task_id, [])
                if q in listeners:
                    listeners.remove(q)
                if not listeners:
                    self._queues.pop(task_id, None)


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

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
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
        try:
            await conn.add_listener(channel, _on_notify)
            while True:
                event = await q.get()
                if event is None:
                    break
                yield event
                if event.state.is_terminal:
                    break
        finally:
            try:
                await conn.remove_listener(channel, _on_notify)
            except Exception:
                logger.debug("[PostgresEventBus] remove_listener failed", exc_info=True)
            await conn.close()
