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
    """
    Why:
    Reject invalid heartbeat cadence early to avoid silent busy-loops.

    How:
    Raise ValueError when the interval is non-positive.
    """
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be greater than zero")


def _heartbeat_if_in_activity(details: dict[str, Any]) -> None:
    """
    Why:
    Keep heartbeat helpers usable in standalone/in-memory execution paths that
    do not run inside a Temporal activity context.

    How:
    Call Temporal heartbeat only when an activity context is active.

    Example:
    _heartbeat_if_in_activity({"stage": "push_input_process", "document_uid": "doc-123"})
    """
    if activity.in_activity():
        activity.heartbeat(details)


async def await_with_heartbeat(
    awaitable: Awaitable[T],
    *,
    heartbeat_details: dict[str, Any] | None = None,
    heartbeat_interval_seconds: float = 20.0,
) -> T:
    """
    Why:
    Provide one await helper for long-running operations that should heartbeat in
    Temporal workers, while still being safe in standalone in-memory execution.

    How:
    Poll the awaitable with a timeout and emit periodic heartbeats only when
    running in a Temporal activity context.

    Example:
    result = await await_with_heartbeat(
        some_async_call(),
        heartbeat_details={"stage": "restore", "document_uid": "doc-123"},
    )
    """
    _validate_heartbeat_interval(heartbeat_interval_seconds)
    details = heartbeat_details or {}
    should_heartbeat = activity.in_activity()
    task = asyncio.ensure_future(awaitable)

    try:
        if not should_heartbeat:
            # In non-Temporal/standalone execution, just await the task directly
            # to avoid periodic wakeups.
            return await task

        activity.heartbeat(details)

        while True:
            done, _ = await asyncio.wait(
                {task},
                timeout=heartbeat_interval_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                return await task
            _heartbeat_if_in_activity(details)
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
    Why:
    Expose a single helper for blocking functions that should run off the event
    loop and still report progress in Temporal workers.

    How:
    Execute the callable with asyncio.to_thread, then delegate heartbeat logic to
    await_with_heartbeat.

    Example:
    await to_thread_with_heartbeat(
        ingestion_service.save_output,
        user,
        metadata,
        output_dir,
        heartbeat_details={"stage": "save_output", "document_uid": "doc-123"},
    )
    """
    return await await_with_heartbeat(
        asyncio.to_thread(func, *args, **kwargs),
        heartbeat_details=heartbeat_details,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
