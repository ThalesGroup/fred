# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import asyncio
from threading import get_ident

import pytest
from fred_core.conversation_trace import TraceDegradation
from fred_runtime.app import conversation_trace_blocks as blocks
from fred_runtime.app.conversation_trace_blocks import (
    TRACE_BLOCK_BYTES,
    TraceBlockRef,
    TraceBlockWriter,
    decode_trace_block,
    encode_trace_block,
)


def test_trace_block_retains_truncated_sse_bytes_and_rejects_incorrect_size() -> None:
    payload = b': keepalive\r\ndata: {"text": "\xc3'
    encoded = encode_trace_block(payload)

    assert decode_trace_block(encoded, len(payload)) == payload
    with pytest.raises(ValueError, match="does not match"):
        decode_trace_block(encoded, len(payload) + 1)
    with pytest.raises(ValueError, match="Invalid trace block size"):
        decode_trace_block(encoded, TRACE_BLOCK_BYTES + 1)


@pytest.mark.asyncio
async def test_writer_publishes_partial_blocks_while_capturing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: dict[str, bytes] = {}
    first_flush = asyncio.Event()
    compression_threads: list[int] = []

    def observed_encode(data: bytes | bytearray) -> bytes:
        compression_threads.append(get_ident())
        return encode_trace_block(data)

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        written[ref.id] = decode_trace_block(data, ref.raw_size)
        first_flush.set()

    monkeypatch.setattr(blocks, "encode_trace_block", observed_encode)
    writer = TraceBlockWriter(publish, block_bytes=4, flush_interval=0.02)
    early = await asyncio.to_thread(writer.append, b"hi")
    assert early is not None
    await asyncio.wait_for(first_flush.wait(), timeout=1)
    assert written[early[0].block_id] == b"hi"

    tail = writer.append(b"last+\xc3")
    assert tail is not None
    assert len(tail) == 2
    result = await writer.finish()

    assert (
        b"".join(
            written[item.block_id][item.offset : item.offset + item.length]
            for item in tail
        )
        == b"last+\xc3"
    )
    assert not result.failed_blocks and result.dropped_bytes == 0
    assert compression_threads
    assert get_ident() not in compression_threads


@pytest.mark.asyncio
async def test_writer_is_bounded_during_an_upload_and_can_capture_the_tail() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    available = asyncio.Event()
    rejected: list[str] = []
    stored: dict[str, bytes] = {}

    async def publish(ref: TraceBlockRef, data: bytes) -> None:
        content = decode_trace_block(data, ref.raw_size)
        if content == b"head":
            started.set()
            await release.wait()
            rejected.append(ref.id)
            available.set()
            raise TimeoutError("storage request expired")
        stored[ref.id] = content

    writer = TraceBlockWriter(publish, block_bytes=4, queue_bytes=8)
    head = writer.append(b"head")
    assert head is not None
    await asyncio.wait_for(started.wait(), timeout=1)
    assert writer.append(b"next") is not None
    assert writer.append(b"lost") is None
    release.set()
    await asyncio.wait_for(available.wait(), timeout=1)
    tail = writer.append(b"tail")
    assert tail is not None
    result = await writer.finish()

    assert result.failed_blocks == frozenset(rejected) == {head[0].block_id}
    assert result.dropped_bytes == 4
    assert result.degradation == TraceDegradation.STORAGE
    assert stored[tail[0].block_id] == b"tail"


@pytest.mark.asyncio
async def test_aborting_writer_releases_pending_bytes_and_stops_storage() -> None:
    issued = asyncio.Event()
    cancelled = asyncio.Event()

    async def publish(_ref: TraceBlockRef, _data: bytes) -> None:
        issued.set()
        try:
            await asyncio.Future[None]()
        finally:
            cancelled.set()

    writer = TraceBlockWriter(publish, block_bytes=4, queue_bytes=8)
    assert writer.append(b"head") is not None
    await asyncio.wait_for(issued.wait(), timeout=1)
    assert writer.append(b"tail") is not None
    writer.abort()
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert writer.append(b"late") is None
    assert writer.remaining_capacity == 0
    with pytest.raises(asyncio.CancelledError):
        await writer.finish()
