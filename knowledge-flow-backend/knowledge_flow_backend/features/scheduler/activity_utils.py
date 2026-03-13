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
from contextlib import suppress
from typing import Any, Awaitable, Callable, TypeVar

from temporalio import activity

T = TypeVar("T")


def _validate_heartbeat_interval(heartbeat_interval_seconds: float) -> None:
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be greater than zero")


async def await_with_heartbeat(
    awaitable: Awaitable[T],
    *,
    heartbeat_details: dict[str, Any] | None = None,
    heartbeat_interval_seconds: float = 20.0,
) -> T:
    """
    Await a long-running operation while emitting periodic Temporal heartbeats.
    """
    _validate_heartbeat_interval(heartbeat_interval_seconds)
    details = heartbeat_details or {}

    activity.heartbeat(details)
    task = asyncio.ensure_future(awaitable)

    try:
        while True:
            done, _ = await asyncio.wait(
                {task},
                timeout=heartbeat_interval_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                return await task
            activity.heartbeat(details)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                # Drain the inner task so cancellation/cleanup is fully observed.
                _ = await task


async def to_thread_with_heartbeat(
    func: Callable[..., T],
    *args: Any,
    heartbeat_details: dict[str, Any] | None = None,
    heartbeat_interval_seconds: float = 20.0,
    **kwargs: Any,
) -> T:
    """
    Run blocking work in a thread while emitting periodic Temporal heartbeats.
    """
    return await await_with_heartbeat(
        asyncio.to_thread(func, *args, **kwargs),
        heartbeat_details=heartbeat_details,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
