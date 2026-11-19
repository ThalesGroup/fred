# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

_Result = TypeVar("_Result")


class BoundedSqlWork:
    """Limit optional work using a shared SQL pool, including driver cleanup."""

    def __init__(self, slots: int, *, queued: int = 0) -> None:
        self._slots = asyncio.Semaphore(slots)
        self._limit = slots + queued
        self._tasks: set[asyncio.Task[object]] = set()

    async def run(
        self, operation: Callable[[], Awaitable[_Result]], *, timeout: float
    ) -> _Result:
        if len(self._tasks) >= self._limit:
            raise TimeoutError("Optional SQL work is saturated")

        async def use_slot() -> _Result:
            async with self._slots:
                return await operation()

        task = asyncio.create_task(use_slot())
        self._tasks.add(task)
        task.add_done_callback(self._forget)
        try:
            # SQLAlchemy can shield transaction and connection cleanup from
            # cancellation. Return at the deadline but keep that task's slot.
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                raise TimeoutError("Optional SQL work exceeded its deadline")
            return task.result()
        finally:
            if not task.done():
                task.cancel()

    def _forget(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()
