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
import logging
import threading
from contextlib import suppress
from typing import Any, Awaitable, Callable, TypeVar

from temporalio import activity, exceptions

from knowledge_flow_backend.common.cancellation import WorkCancelled, cancellation_scope

logger = logging.getLogger(__name__)

T = TypeVar("T")

# How long a cancelled activity holds on for its worker thread to reach a
# cancellation checkpoint before detaching from it. Generous enough for one
# in-flight embedding sub-batch (~2-3s) plus a transient-retry backoff; a
# thread stuck longer (e.g. one stalled provider call) is detached with a
# warning and its output is discarded by the persist/purge fences.
THREAD_CANCEL_DRAIN_MAX_SECONDS = 30.0


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
    heartbeat_interval_seconds: float = 5.0,
    cancel_on_exit: bool = True,
) -> T:
    """
    Why:
    Provide one await helper for long-running operations that should heartbeat in
    Temporal workers, while still being safe in standalone in-memory execution.

    How:
    Poll the awaitable with a timeout and emit periodic heartbeats only when
    running in a Temporal activity context. `cancel_on_exit=False` leaves the
    task running when this helper exits abnormally — for callers that keep their
    own handle to it and want to drain it instead (see to_thread_with_heartbeat).

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
        if cancel_on_exit and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                _ = await task


async def to_thread_with_heartbeat(
    func: Callable[..., T],
    *args: Any,
    heartbeat_details: dict[str, Any] | None = None,
    heartbeat_interval_seconds: float = 5.0,
    drain_on_cancel: bool = False,
    **kwargs: Any,
) -> T:
    """
    Why:
    Expose a single helper for blocking functions that should run off the event
    loop and still report progress in Temporal workers.

    How:
    Execute the callable with asyncio.to_thread, then delegate heartbeat logic to
    await_with_heartbeat. Pass `drain_on_cancel=True` when `func` checks
    cancellation checkpoints (`raise_if_cancelled`): on activity cancellation the
    helper then holds the activity open until the thread actually stopped, so
    everything the workflow does next (emit the cancelled event, delete the
    document, purge artifacts) happens strictly after the thread's last write.
    Leave it False for work without checkpoints — draining would only delay the
    cancellation by the full bound for nothing.

    Example:
    await to_thread_with_heartbeat(
        ingestion_service.save_output,
        user,
        metadata,
        output_dir,
        heartbeat_details={"stage": "save_output", "document_uid": "doc-123"},
    )
    """
    # The thread cannot be killed, so tell it to stop instead: loops inside
    # `func` that check `raise_if_cancelled` abandon their remaining work at the
    # next boundary rather than running to completion for a document that was
    # cancelled minutes ago (#2315). Entered before the thread starts so the
    # context copied into it carries this scope's Event.
    with cancellation_scope() as cancel_signal:
        # The drain tracks the *thread* (event + outcome), not the asyncio task
        # wrapping it: cancelling the activity can cancel that task while the
        # thread is still running, so the task's state says nothing about
        # whether the thread stopped writing.
        thread_done = threading.Event()
        thread_outcome: dict[str, BaseException | None] = {}

        def _run() -> T:
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                thread_outcome["exception"] = exc
                raise
            else:
                thread_outcome["exception"] = None
                return result
            finally:
                thread_done.set()

        task = asyncio.ensure_future(asyncio.to_thread(_run))
        try:
            return await await_with_heartbeat(
                task,
                heartbeat_details=heartbeat_details,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                cancel_on_exit=False,
            )
        except asyncio.CancelledError:
            # Signal explicitly before draining — the scope also sets it on
            # exit, but the drain below needs the thread reacting *now*.
            cancel_signal.set()
            if drain_on_cancel:
                await _drain_cancelled_thread(
                    thread_done,
                    thread_outcome,
                    heartbeat_details=heartbeat_details or {},
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                )
            raise
        finally:
            if not task.done():
                task.cancel()
            # Always consume the task's outcome. The drain reads the thread's
            # result through its own channel (thread_outcome), so without this
            # the task's WorkCancelled sat unretrieved and asyncio's GC-time
            # handler dumped it as an ERROR stacktrace — for an event already
            # logged as one INFO line. Awaiting a finished task is free; every
            # useful outcome was already delivered to the caller above.
            with suppress(BaseException):
                _ = await task


async def _drain_cancelled_thread(
    thread_done: threading.Event,
    thread_outcome: dict[str, BaseException | None],
    *,
    heartbeat_details: dict[str, Any],
    heartbeat_interval_seconds: float,
) -> None:
    """Hold a cancelled activity open until its worker thread stops writing.

    Without this, activity cancellation returned immediately while the
    unkillable thread was still mid-loop: the workflow's compensation purged the
    document's artifacts, then the thread kept indexing — six more batches of
    vectors observed landing *after* the purge, orphaned in the index (#2315).
    Waiting here restores the ordering "last write, then cleanup".

    Bounded wait: a thread stuck in one long provider call past the bound is
    detached with a warning — the persist/purge fences and the vectorization
    cancel handler then discard whatever it still writes. The expected outcome
    is the thread raising WorkCancelled at its next checkpoint within seconds;
    that is logged as one INFO line, not a stacktrace, because it is the normal
    end of a cancelled ingestion.
    """
    loop = asyncio.get_running_loop()
    signalled_at = loop.time()
    deadline = signalled_at + THREAD_CANCEL_DRAIN_MAX_SECONDS
    next_heartbeat = signalled_at + heartbeat_interval_seconds
    label = f"stage={heartbeat_details.get('stage', '?')} document_uid={heartbeat_details.get('document_uid', '?')}"
    while not thread_done.is_set():
        now = loop.time()
        if now >= deadline:
            logger.warning(
                "[SCHEDULER][CANCEL] %s: worker thread still busy %.0fs after the cancel signal; detaching (it stops at its next checkpoint and its output is discarded)",
                label,
                THREAD_CANCEL_DRAIN_MAX_SECONDS,
            )
            return
        # Fine-grained tick so the drain notices the thread stopping within
        # ~250ms; heartbeats keep their own slower cadence.
        await asyncio.sleep(min(0.25, heartbeat_interval_seconds, deadline - now))
        if loop.time() >= next_heartbeat:
            _heartbeat_if_in_activity(heartbeat_details)
            next_heartbeat = loop.time() + heartbeat_interval_seconds
    exc = thread_outcome.get("exception")
    elapsed = loop.time() - signalled_at
    if exc is None or isinstance(exc, WorkCancelled):
        logger.info(
            "[SCHEDULER][CANCEL] %s: worker thread stopped %.1fs after the cancel signal",
            label,
            elapsed,
        )
    else:
        logger.warning(
            "[SCHEDULER][CANCEL] %s: worker thread ended with %s during cancellation: %s",
            label,
            type(exc).__name__,
            exc,
        )


def raise_if_document_deleted(persisted: bool, document_uid: str) -> None:
    """Abort the activity when the document it was about to process is gone.

    Takes the result of an `IngestionService.persist_progress` call: False
    means the document was deleted meanwhile (a cancelled ingestion erases it,
    #2315). Non-retryable — retrying cannot bring the document back, and the
    work would be thrown away again.

    Only for the up-front stage stamp, to skip work that is already pointless.
    Later writes just let `persist_progress` return False: it discards the
    artifacts they wrote and the activity finishes normally.
    """
    if not persisted:
        raise exceptions.ApplicationError(
            f"Document {document_uid} was deleted mid-flight; nothing to process.",
            non_retryable=True,
        )
