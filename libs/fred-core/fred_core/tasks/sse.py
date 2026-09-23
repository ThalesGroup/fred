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
from contextlib import suppress
from typing import TYPE_CHECKING, AsyncGenerator, AsyncIterator, Awaitable, Callable

from fred_core.tasks.models import TaskEvent, TaskState

if TYPE_CHECKING:
    from fred_core.tasks.service import TaskService

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


async def with_heartbeat(source: AsyncIterator[str]) -> AsyncGenerator[str, None]:
    """Interleave SSE heartbeat comments while waiting for the next event."""
    source_iter = source.__aiter__()

    async def _advance() -> str:
        return await source_iter.__anext__()

    pending: asyncio.Task[str] = asyncio.create_task(_advance())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_INTERVAL)
            if pending in done:
                try:
                    yield pending.result()
                except StopAsyncIteration:
                    return
                pending = asyncio.create_task(_advance())
            else:
                yield ": ping\n\n"
    finally:
        pending.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await pending  # Wait for cancellation to settle before closing the source.
        close = getattr(source_iter, "aclose", None)
        if close is not None:
            await close()


def _sse_frame(seq: int, data_json: str) -> str:
    return f"id: {seq}\ndata: {data_json}\n\n"


async def task_event_stream(
    service: TaskService,
    task_id: str,
    *,
    after_seq: int,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """SSE body for ``GET /tasks/{task_id}/events`` — shared by every backend.

    Why this exists:
    - Both backends expose the same task SSE endpoint. This is the single
      implementation, so they cannot drift (e.g. one forgetting read-time
      reconciliation and hanging on a dead workflow). Per-request auth and
      ``Last-Event-ID`` parsing stay in each app's route.

    How to use (in a route, after auth + parsing ``after_seq``):
    ```python
    return StreamingResponse(
        with_heartbeat(
            task_event_stream(
                service, task_id,
                after_seq=after_seq,
                is_disconnected=request.is_disconnected,
            )
        ),
        media_type="text/event-stream",
    )
    ```

    Behaviour: read-time reconcile → subscribe → replay events with
    ``seq > after_seq`` → stream live bus events until terminal or client
    disconnect. A terminal state closes the stream. Every heartbeat interval,
    an idle stream checks the durable journal to recover missed notifications.

    Ordering matters: the live subscription is opened **before** the replay, so an
    event published in the gap between the replay snapshot and going live is
    buffered rather than lost (a lost terminal event would hang the stream). Live
    events are deduped against the replay by ``seq``, which is monotonic per task.
    """
    # Read-time reconciliation: if the backing workflow is gone/failed, drive the
    # task terminal now so the stream reflects it and closes instead of hanging.
    try:
        await service.reconcile_task(task_id)
    except Exception:
        logger.warning(
            "task_event_stream: reconcile failed for task %s", task_id, exc_info=True
        )

    # Attach the listener first; anything published from here on is buffered.
    subscription = await service.bus.open_subscription(task_id)
    pending_event: asyncio.Future[TaskEvent] | None = None
    try:
        last_seq = after_seq
        for event in await service.replay(task_id, after_seq=after_seq):
            last_seq = max(last_seq, event.seq)
            yield _sse_frame(event.seq, event.model_dump_json())
            if event.state.is_terminal:
                return

        run = await service.get_run(task_id)
        if run is None or TaskState(run.state).is_terminal:
            # Catch a committed terminal event even when its notification was lost.
            for event in await service.replay(task_id, after_seq=last_seq):
                last_seq = event.seq
                yield _sse_frame(event.seq, event.model_dump_json())
                if event.state.is_terminal:
                    return
            # Already terminal: the terminal event may have fired in the race
            # window and be sitting in the buffer — flush it, then stop instead
            # of blocking on a live stream that will never produce more.
            for buffered in subscription.drain_ready():
                if buffered.seq <= last_seq:
                    continue
                yield _sse_frame(buffered.seq, buffered.model_dump_json())
                if buffered.state.is_terminal:
                    return
            return

        live = subscription.__aiter__()
        pending_event = asyncio.ensure_future(anext(live))
        while not await is_disconnected():
            done, _ = await asyncio.wait({pending_event}, timeout=HEARTBEAT_INTERVAL)
            if not done:
                # Notifications accelerate delivery; the journal recovers missed publishes.
                for event in await service.replay(task_id, after_seq=last_seq):
                    last_seq = event.seq
                    yield _sse_frame(event.seq, event.model_dump_json())
                    if event.state.is_terminal:
                        return
                continue
            try:
                live_event = pending_event.result()
            except StopAsyncIteration:
                return
            if live_event.seq > last_seq:
                last_seq = live_event.seq
                yield _sse_frame(live_event.seq, live_event.model_dump_json())
                if live_event.state.is_terminal:
                    return
            pending_event = asyncio.ensure_future(anext(live))
    finally:
        if pending_event is not None:
            pending_event.cancel()
            with suppress(asyncio.CancelledError, Exception):
                # Settle the pending read before closing its subscription.
                await pending_event
        await subscription.aclose()
