# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import asyncio
from pathlib import Path

import httpx
import pytest
from fred_core.conversation_trace import TRACE_SSE_PAGE_FRAMES, TraceSseEnding
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_runtime.app.conversation_trace_artifacts import (
    HttpTurnBuffer,
    RecordedHttpAttempt,
    TraceHttpArtifactStore,
)
from fred_runtime.app.conversation_trace_blocks import (
    TRACE_BLOCK_FILE,
    TraceBlockRef,
    TraceBlockWriter,
)
from fred_runtime.app.conversation_trace_sse import SsePageData


@pytest.mark.asyncio
async def test_long_turn_preserves_last_parallel_stream_and_exact_failed_tail(
    tmp_path: Path,
) -> None:
    store = TraceHttpArtifactStore(LocalFilesystem(root=str(tmp_path)))
    stored = asyncio.Queue[str]()

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        await store.publish("synthetic", ref.id, {TRACE_BLOCK_FILE: data})
        stored.put_nowait(ref.id)

    writer = TraceBlockWriter(publish)
    buffer = HttpTurnBuffer(block_writer=writer)
    frame = b'data: {"choices":[{"delta":{"reasoning":"' + b"x" * 360 + b'"}}]}\n\n'
    terminal = b"data: [DONE]\n\n"
    cut = b'data: {"choices":[{"delta":{"content":"unfinished'
    request_body = b'{"messages":[]}'

    def begin(number: int) -> RecordedHttpAttempt:
        attempt = buffer.begin_http(
            httpx.Request(
                "POST", "https://provider.invalid/chat", content=request_body
            ),
            call_id=f"call-{number}",
            number=1,
            model="synthetic",
        )
        assert attempt is not None
        attempt.headers(
            httpx.Response(200, headers={"content-type": "text/event-stream"})
        )
        return attempt

    def observe(attempt: RecordedHttpAttempt, data: bytes) -> None:
        attempt.chunk(data)
        attempt.sse_chunk(data)

    def finish(attempt: RecordedHttpAttempt, *, interrupted: bool = False) -> None:
        error = (
            httpx.RemoteProtocolError("synthetic interrupted stream")
            if interrupted
            else None
        )
        attempt.finish(body_complete=not interrupted, failed=interrupted, error=error)
        attempt.finish_sse(error)

    try:
        for number in range(138):
            attempt = begin(number)
            observe(attempt, frame * 564 + terminal)
            finish(attempt)
            writer.flush()
            await asyncio.wait_for(stored.get(), timeout=5)

        earlier, failed = begin(138), begin(139)
        for _ in range(6):
            observe(earlier, frame * 94)
            observe(failed, frame * 94)
        observe(earlier, terminal)
        observe(failed, cut)
        finish(earlier)
        finish(failed, interrupted=True)
        buffer.close()
        drain = await writer.finish()
        assert not drain.failed_blocks
        assert not drain.dropped_bytes
        assert len(buffer.attempts) == 140
        assert (
            sum(attempt.response_body.observed for attempt in buffer.attempts)
            >= 28 * 1024**2
        )
        assert (
            sum(attempt.sse.frame_count for attempt in buffer.attempts if attempt.sse)
            >= 78_610
        )

        lane = failed.sse
        assert lane is not None
        lane.prepare_provider()
        summary = lane.summary(stored=True)
        assert summary.page_starts_ms
        assert summary.ending is TraceSseEnding.TRUNCATED
        files = store.http_files(failed)
        files.update(store.sse_files(lane))
        assert not any(name.startswith("sse-0") for name in files)
        await store.publish("synthetic", failed.ref, files)
        manifest = await store.read_sse_page_manifest("synthetic", failed.ref)
        page = SsePageData.model_validate_json(
            await store.read_block_ranges("synthetic", manifest.pages[-1])
        )
        assert len(page.frames) == 565 % TRACE_SSE_PAGE_FRAMES
        last = page.frames[-1]
        assert last.offset is not None and last.at_ms >= page.frames[0].at_ms
        assert (
            await store.read_body_range("synthetic", failed.ref, last.offset, last.size)
            == cut
        )
    finally:
        writer.abort()
        await store.close()
