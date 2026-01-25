# Copyright Thales 2025
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
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List

from fred_core.scheduler.scheduler_structures import SchedulerTaskEvent


class SchedulerEventBus(ABC):
    @abstractmethod
    async def publish(self, event: SchedulerTaskEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, task_id: str) -> AsyncIterator[SchedulerTaskEvent]:
        raise NotImplementedError


class InMemorySchedulerEventBus(SchedulerEventBus):
    def __init__(self, max_queue_size: int = 0) -> None:
        self._max_queue_size = max_queue_size
        self._subscribers: Dict[str, List[asyncio.Queue[SchedulerTaskEvent]]] = {}

    def _register(self, task_id: str) -> asyncio.Queue[SchedulerTaskEvent]:
        queue: asyncio.Queue[SchedulerTaskEvent] = asyncio.Queue(
            maxsize=self._max_queue_size
        )
        self._subscribers.setdefault(task_id, []).append(queue)
        return queue

    def _unregister(
        self, task_id: str, queue: asyncio.Queue[SchedulerTaskEvent]
    ) -> None:
        queues = self._subscribers.get(task_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(task_id, None)

    async def publish(self, event: SchedulerTaskEvent) -> None:
        queues = list(self._subscribers.get(event.task_id, []))
        for queue in queues:
            await queue.put(event)

    async def subscribe(self, task_id: str) -> AsyncIterator[SchedulerTaskEvent]:
        queue = self._register(task_id)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.is_terminal():
                    break
        finally:
            self._unregister(task_id, queue)
