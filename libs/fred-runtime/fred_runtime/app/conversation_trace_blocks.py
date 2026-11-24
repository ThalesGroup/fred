# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Lossless trace blocks assembled in bounded memory and published off the chat path."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from contextlib import suppress
from contextvars import Context
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4

import zstandard
from fred_core.conversation_trace import TraceDegradation

TRACE_BLOCK_BYTES = 1024 * 1024
TRACE_BLOCK_FILE = "block.zst"
TRACE_WRITER_QUEUE_BYTES = 4 * TRACE_BLOCK_BYTES
TRACE_CRITICAL_TAIL_BYTES = 64 * 1024
_COMPRESSION_LEVEL = 3


@dataclass(frozen=True, slots=True)
class TraceBlockRef:
    id: str
    raw_size: int


@dataclass(frozen=True, slots=True)
class TraceBlockRange:
    block_id: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class TraceBlockDrain:
    failed_blocks: frozenset[str]
    dropped_bytes: int
    degradation: TraceDegradation | None


class TraceBlockFailure(Exception):
    def __init__(self, reason: TraceDegradation) -> None:
        super().__init__(reason.value)
        self.reason = reason


def encode_trace_block(data: bytes | bytearray) -> bytes:
    if not 0 < len(data) <= TRACE_BLOCK_BYTES:
        raise ValueError("Invalid trace block size")
    return zstandard.ZstdCompressor(
        level=_COMPRESSION_LEVEL, write_checksum=True
    ).compress(data)


def decode_trace_block(data: bytes, raw_size: int | None = None) -> bytes:
    if raw_size is not None and not 0 < raw_size <= TRACE_BLOCK_BYTES:
        raise ValueError("Invalid trace block size")
    try:
        params = zstandard.get_frame_parameters(data)
        if (
            not 0 < params.content_size <= TRACE_BLOCK_BYTES
            or (raw_size is not None and params.content_size != raw_size)
            or params.window_size > TRACE_BLOCK_BYTES
        ):
            raise ValueError("Trace block header does not match its index")
        return zstandard.ZstdDecompressor().decompress(data, allow_extra_data=False)
    except zstandard.ZstdError as exc:
        raise ValueError("Invalid compressed trace block") from exc


class TraceBlockWriter:
    """Accept trace bytes from any thread and publish each sealed block once.

    A returned range names logical bytes, which become durable only when the
    caller's publication callback succeeds. The pending-byte budget includes
    the active upload. Capture producers never await compression or storage.
    """

    def __init__(
        self,
        publish: Callable[[TraceBlockRef, bytes], Awaitable[None]],
        *,
        executor: Executor | None = None,
        block_bytes: int = TRACE_BLOCK_BYTES,
        queue_bytes: int = TRACE_WRITER_QUEUE_BYTES,
        flush_interval: float = 5.0,
    ) -> None:
        if not 0 < block_bytes <= TRACE_BLOCK_BYTES or queue_bytes < block_bytes:
            raise ValueError("Invalid trace writer byte bounds")
        if flush_interval <= 0:
            raise ValueError("Invalid trace writer flush interval")
        self._publish = publish
        self._executor = executor
        self._block_bytes = block_bytes
        self._queue_bytes = queue_bytes
        self._flush_interval = flush_interval
        self._loop = asyncio.get_running_loop()
        self._lock = Lock()
        self._changed = asyncio.Event()
        self._ready: deque[tuple[TraceBlockRef, bytearray]] = deque()
        self._tail = bytearray()
        self._tail_id: str | None = None
        self._flush_at = 0.0
        self._pending_bytes = 0
        self._dropped_bytes = 0
        self._failed_blocks: set[str] = set()
        self._degradation: TraceDegradation | None = None
        self._wake_pending = False
        self._closed = False
        self._worker = self._loop.create_task(self._run(), context=Context())

    def append(self, data: bytes) -> tuple[TraceBlockRange, ...] | None:
        """Queue a byte span or return None and account for the dropped bytes."""
        return self._append(data, critical=False)

    def append_critical(self, data: bytes) -> tuple[TraceBlockRange, ...] | None:
        """Use the recovery reserve to retry a previously rejected provider tail."""
        if len(data) > TRACE_CRITICAL_TAIL_BYTES:
            return None
        return self._append(data, critical=True)

    def _append(
        self, data: bytes, *, critical: bool
    ) -> tuple[TraceBlockRange, ...] | None:
        if not data:
            return ()
        ranges: list[TraceBlockRange] = []
        with self._lock:
            if self._closed:
                return None
            reserve = TRACE_CRITICAL_TAIL_BYTES if critical else 0
            if len(data) > self._queue_bytes + reserve - self._pending_bytes:
                if not critical:
                    self._dropped_bytes += len(data)
                return None
            if critical:
                self._dropped_bytes = max(0, self._dropped_bytes - len(data))
            self._pending_bytes += len(data)
            pos = 0
            view = memoryview(data)
            need_wake = self._tail_id is None
            while pos < len(data):
                if self._tail_id is None:
                    self._tail_id = uuid4().hex
                    self._flush_at = monotonic() + self._flush_interval
                offset = len(self._tail)
                count = min(self._block_bytes - offset, len(data) - pos)
                self._tail.extend(view[pos : pos + count])
                ranges.append(TraceBlockRange(self._tail_id, offset, count))
                pos += count
                if len(self._tail) == self._block_bytes:
                    self._seal_locked()
                    need_wake = True
            if need_wake:
                self._wake_locked()
        return tuple(ranges)

    def flush(self) -> None:
        """Seal the current block without awaiting its publication."""
        with self._lock:
            if self._tail_id is not None:
                self._seal_locked()
                self._wake_locked()

    @property
    def remaining_capacity(self) -> int:
        with self._lock:
            return (
                0 if self._closed else max(0, self._queue_bytes - self._pending_bytes)
            )

    @property
    def value_capacity(self) -> int:
        return self._queue_bytes

    async def finish(self) -> TraceBlockDrain:
        """Seal the remaining bytes and wait for the diagnostic worker."""
        with self._lock:
            self._closed = True
            self._wake_locked()
        return await asyncio.shield(self._worker)

    def abort(self) -> None:
        """Release pending bytes and stop an abandoned diagnostic write."""
        with self._lock:
            self._closed = True
            self._ready.clear()
            self._tail.clear()
            self._tail_id = None
        self._loop.call_soon_threadsafe(self._worker.cancel, context=Context())

    def _seal_locked(self) -> None:
        assert self._tail_id is not None
        ref = TraceBlockRef(self._tail_id, len(self._tail))
        self._ready.append((ref, self._tail))
        self._tail = bytearray()
        self._tail_id = None

    def _wake_locked(self) -> None:
        if not self._wake_pending:
            self._wake_pending = True
            self._loop.call_soon_threadsafe(self._wake, context=Context())

    def _wake(self) -> None:
        with self._lock:
            self._wake_pending = False
        self._changed.set()

    async def _run(self) -> TraceBlockDrain:
        while True:
            self._changed.clear()
            with self._lock:
                timeout = (
                    self._flush_at - monotonic() if self._tail_id is not None else None
                )
                if timeout is not None and (self._closed or timeout <= 0):
                    self._seal_locked()
                block = self._ready.popleft() if self._ready else None
                if block is None and self._closed:
                    return TraceBlockDrain(
                        frozenset(self._failed_blocks),
                        self._dropped_bytes,
                        self._degradation
                        or (TraceDegradation.QUEUE if self._dropped_bytes else None),
                    )
            if block is None:
                with suppress(TimeoutError):
                    async with asyncio.timeout(timeout):
                        await self._changed.wait()
                continue
            ref, data = block
            try:
                encoded = await self._loop.run_in_executor(
                    self._executor, encode_trace_block, data
                )
                await self._publish(ref, encoded)
            except Exception as exc:
                self._failed_blocks.add(ref.id)
                self._degradation = self._degradation or (
                    exc.reason
                    if isinstance(exc, TraceBlockFailure)
                    else TraceDegradation.STORAGE
                )
            finally:
                with self._lock:
                    self._pending_bytes -= ref.raw_size
