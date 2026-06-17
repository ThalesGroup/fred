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
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable

from fred_core.tasks.models import TaskState

if TYPE_CHECKING:
    from fred_core.tasks.service import TaskService

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


async def with_heartbeat(source: AsyncIterator[str]) -> AsyncIterator[str]:
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
        if pending and not pending.done():
            pending.cancel()


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

    Behaviour: read-time reconcile → replay events with ``seq > after_seq`` →
    stream live bus events until terminal or client disconnect. A terminal state
    closes the stream.
    """
    # Read-time reconciliation: if the backing workflow is gone/failed, drive the
    # task terminal now so the stream reflects it and closes instead of hanging.
    try:
        await service.reconcile_task(task_id)
    except Exception:
        logger.warning(
            "task_event_stream: reconcile failed for task %s", task_id, exc_info=True
        )

    for event in await service.replay(task_id, after_seq=after_seq):
        yield _sse_frame(event.seq, event.model_dump_json())
        if event.state.is_terminal:
            return

    run = await service.get_run(task_id)
    if run is None or TaskState(run.state).is_terminal:
        return

    async for live_event in service.bus.subscribe(task_id):
        if await is_disconnected():
            break
        yield _sse_frame(live_event.seq, live_event.model_dump_json())
        if live_event.state.is_terminal:
            break
