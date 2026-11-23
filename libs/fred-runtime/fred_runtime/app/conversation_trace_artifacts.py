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


"""Bounded, private HTTP evidence for one admitted conversation turn."""

from __future__ import annotations

import asyncio
import re
from _thread import LockType
from base64 import b64encode
from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Sequence
from contextvars import Context
from dataclasses import dataclass, field
from hashlib import sha256
from itertools import islice, pairwise
from threading import Lock
from time import monotonic
from typing import Annotated, Literal, TypeVar
from uuid import uuid4

import httpx
import httpx2
from aiohttp import ClientPayloadError
from fred_core.conversation_trace import (
    TRACE_HEADER_VALUE_BYTES,
    TRACE_HTTP_CHUNK_BYTES,
    TRACE_MAX_NORMALIZATION_REWRITES,
    EvidenceReference,
    TraceHttpAttempt,
    TraceHttpBody,
    TraceHttpCompleteness,
    TraceHttpEvidence,
    TraceHttpFailureStage,
    TraceModelEvidence,
    TraceModelOutputState,
    TraceModelSnapshot,
    TraceNormalization,
    TraceNormalizationRewrite,
    TraceNormalizationStatus,
    TraceSseEnding,
    TraceSseHeaders,
    TraceToolEvidence,
    TraceToolSource,
)
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.model.http_capture import HttpAttempt, HttpRequest
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic import BaseModel, Field, TypeAdapter

from fred_runtime.app.conversation_trace_blocks import (
    TRACE_BLOCK_BYTES,
    TRACE_BLOCK_FILE,
    TRACE_CRITICAL_TAIL_BYTES,
    TRACE_WRITER_QUEUE_BYTES,
    TraceBlockRange,
    TraceBlockWriter,
    decode_trace_block,
    encode_trace_block,
)
from fred_runtime.app.conversation_trace_model import (
    RecordedModelCall,
    SnapshotWork,
    stage_snapshot,
)
from fred_runtime.app.conversation_trace_sse import (
    RecordedSseLane,
    SseClock,
    SsePageManifest,
)
from fred_runtime.app.conversation_trace_storage import TraceObjectIO, storage_deadline
from fred_runtime.app.conversation_trace_tools import (
    RecordedToolCall,
)

_MAX_COUNT = 2**31 - 1
_HTTP_BODY_PAGE_BLOCKS = 8
_HTTP_BODY_INDEX_SPANS = 1024
_MAX_PROVIDER_TAILS = 16
_SNAPSHOT_MANIFEST_MAX_BYTES = 512 * 1024
# These object names are also used by existing compressed captures.
_MODEL_MANIFEST_FILE = "model-v1.json"
_TOOL_MANIFEST_FILE = "tool-v1.json"
_MAX_DISCARDED_BODIES = 8
_MAX_DISCARDED_PER_SEGMENT = 2
_Snapshot = TypeVar("_Snapshot")
_NORMALIZATION_REWRITES_PER_SEGMENT = 128
_IDENT = re.compile(r"[a-zA-Z0-9_.:-]{1,255}\Z")
_BLOCK_ID = re.compile(r"[0-9a-f]{32}\Z")
_REQUEST_HEADERS = frozenset(
    {"accept", "content-type", "content-encoding", "content-length"}
)
_REPLAY_TRANSPORT_HEADERS = _REQUEST_HEADERS.union(
    {"accept-encoding", "authorization", "connection", "host", "user-agent"}
)
_REQUEST_IDS = (
    "x-request-id",
    "apim-request-id",
    "x-correlation-id",
    "request-id",
    "x-amzn-requestid",
    "x-goog-request-id",
)
_RESPONSE_HEADERS = _REQUEST_HEADERS.union(
    _REQUEST_IDS, {"retry-after", "date", "cache-control", "x-accel-buffering"}
)
_RESPONSE_HEADER_BYTES = frozenset(name.encode("ascii") for name in _RESPONSE_HEADERS)


def _headers(
    source: httpx.Headers | httpx2.Headers, allow: frozenset[str]
) -> dict[str, str]:
    return {
        name: source[name][:TRACE_HEADER_VALUE_BYTES]
        for name in allow
        if name in source
    }


def _has_replayable_bearer_headers(
    headers: httpx.Headers | httpx2.Headers, authority: str
) -> bool:
    authorization = headers.get_list("authorization")
    hosts = headers.get_list("host")
    return (
        len(authorization) == 1
        and authorization[0][:7].lower() == "bearer "
        and len(hosts) == 1
        and hosts[0].lower() == authority.lower()
        and all(
            len(headers.get(name, "")) <= TRACE_HEADER_VALUE_BYTES
            for name in ("accept", "content-type")
        )
        and all(
            name in _REPLAY_TRANSPORT_HEADERS or name.startswith("x-stainless-")
            for name in headers.keys()
        )
    )


def trace_response_headers(source: Iterable[tuple[bytes, bytes]]) -> dict[str, str]:
    """Keep only the bounded diagnostic allowlist at either response boundary."""
    headers: dict[str, str] = {}
    for raw_name, value in source:
        raw_name = raw_name.lower()
        if raw_name not in _RESPONSE_HEADER_BYTES:
            continue
        name = raw_name.decode("ascii")
        previous = headers.get(name)
        prefix = f"{previous}, " if previous is not None else ""
        budget = TRACE_HEADER_VALUE_BYTES - len(prefix)
        if budget > 0:
            headers[name] = prefix + value[:budget].decode("latin-1")
    return headers


def safe_identifier(value: str | None) -> str | None:
    return value if value and _IDENT.fullmatch(value) else None


def _sse_ending(error: Exception | None) -> TraceSseEnding:
    if isinstance(
        error, (httpx.TimeoutException, httpx2.TimeoutException, TimeoutError)
    ):
        return TraceSseEnding.TIMEOUT
    if isinstance(
        error,
        (httpx.RemoteProtocolError, httpx2.RemoteProtocolError, ClientPayloadError),
    ):
        return TraceSseEnding.TRUNCATED
    return (
        TraceSseEnding.TRANSPORT_ERROR if error is not None else TraceSseEnding.CLOSED
    )


@dataclass(slots=True)
class _BodySpan:
    start: int
    block_id: str
    block_offset: int
    length: int

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True, slots=True)
class _RejectedProviderTail:
    end: int
    data: bytes


@dataclass(slots=True)
class _Body:
    size: int = 0
    observed: int = 0
    logical_size: int = 0
    spans: list[_BodySpan] = field(default_factory=list)

    def count_transport(self, data: bytes) -> None:
        self.observed = min(_MAX_COUNT, self.observed + len(data))

    def append(self, data: bytes, writer: TraceBlockWriter) -> bool:
        start = self.logical_size
        self.logical_size += len(data)
        ranges = writer.append(data)
        if ranges is None:
            return False
        self.retain_ranges(start, ranges)
        return True

    def retain_ranges(self, start: int, ranges: tuple[TraceBlockRange, ...]) -> None:
        for part in ranges:
            previous = self.spans[-1] if self.spans else None
            if (
                previous is not None
                and previous.end == start
                and previous.block_id == part.block_id
                and previous.block_offset + previous.length == part.offset
            ):
                previous.length += part.length
            else:
                self.spans.append(
                    _BodySpan(start, part.block_id, part.offset, part.length)
                )
            self.size += part.length
            start += part.length

    def discard_failed_blocks(self, failed_blocks: frozenset[str]) -> None:
        self.spans = [part for part in self.spans if part.block_id not in failed_blocks]
        self.size = sum(part.length for part in self.spans)

    def has_range(self, offset: int, size: int) -> bool:
        if size <= 0 or offset < 0:
            return False
        end = offset + size
        index = bisect_right(self.spans, offset, key=lambda part: part.end)
        while index < len(self.spans):
            part = self.spans[index]
            if part.start > offset:
                return False
            if part.end >= end:
                return True
            offset = part.end
            index += 1
        return False

    def retained_complete(self) -> bool:
        return self.size == self.logical_size and (
            self.logical_size > 0 or self.observed == 0
        )


@dataclass(slots=True)
class DiscardedResponseDrains:
    """Pod-wide capacity for diagnostics that temporarily own a provider stream."""

    active: set[asyncio.Task[None]] = field(default_factory=set)

    def start(self, operation: Coroutine[object, object, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(operation, context=Context())
        self.active.add(task)
        task.add_done_callback(self.active.discard)
        return task


@dataclass(slots=True)
class RecordedHttpAttempt:
    buffer: HttpTurnBuffer
    ref: str
    call_id: str
    number: int
    model: str | None
    method: str
    target: str
    request_headers: dict[str, str]
    tool_ref: str | None = None
    bearer_replay: bool = False
    sse: RecordedSseLane | None = None
    streams_sse: bool = False
    started: float = field(default_factory=monotonic)
    ended: float | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    status: int | None = None
    request_body: _Body = field(default_factory=_Body)
    response_body: _Body = field(default_factory=_Body)
    request_complete: bool = False
    response_complete: bool = False
    failed: bool = False
    draining_discarded_body: bool = False
    normalization_status: TraceNormalizationStatus = (
        TraceNormalizationStatus.UNAVAILABLE
    )
    rewrites: list[TraceNormalizationRewrite] = field(default_factory=list)
    normalization_partial: bool = False

    @property
    def remaining_budget(self) -> int:
        with self.buffer.lock:
            if self.buffer.closed and not self.draining_discarded_body:
                return 0
            return self.buffer.block_writer.remaining_capacity

    def defer_discarded_body(self, drain: Callable[[], Awaitable[None]]) -> bool:
        drains = self.buffer.discarded_drains
        pending = self.buffer.discarded_pending
        if (
            self.buffer.closed
            or drains is None
            or len(drains.active) >= _MAX_DISCARDED_BODIES
            or len(pending) >= _MAX_DISCARDED_PER_SEGMENT
        ):
            return False

        async def own_transport() -> None:
            try:
                await drain()
            finally:
                self.draining_discarded_body = False

        self.draining_discarded_body = True
        task = drains.start(own_transport())
        pending.add(task)
        task.add_done_callback(pending.discard)
        return True

    def headers(self, response: httpx.Response | httpx2.Response) -> None:
        self.status = response.status_code
        self.response_headers = trace_response_headers(response.headers.raw)
        is_sse = response.is_success and (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            == "text/event-stream"
        )
        if not is_sse:
            self.normalization_status = TraceNormalizationStatus.SKIPPED
        if self.sse is not None:
            self.sse.headers_ms = self.buffer.sse.at(monotonic())
            self.sse.headers = self.response_headers
            self.streams_sse = is_sse

    def chunk(self, data: bytes) -> None:
        with self.buffer.lock:
            if not self.buffer.closed or self.draining_discarded_body:
                self.response_body.count_transport(data)
                if not self.streams_sse and not self.response_body.append(
                    data, self.buffer.block_writer
                ):
                    self.buffer.incomplete = True

    def finish(
        self,
        *,
        body_complete: bool,
        failed: bool = False,
        error: Exception | None = None,
    ) -> None:
        if self.ended is None:
            self.ended = monotonic()
            self.response_complete = body_complete
            self.failed = failed
            if self.sse is not None and not self.streams_sse:
                if self.status is None:
                    ending = _sse_ending(error)
                elif self.status >= 400:
                    ending = TraceSseEnding.HTTP_REJECTED
                else:
                    ending = TraceSseEnding.NOT_SSE
                self.sse.finish(self.ended, ending)

    def sse_chunk(self, data: bytes) -> None:
        if self.sse is None or not self.streams_sse:
            return
        with self.buffer.lock:
            if not self.buffer.closed and self.sse.end_ms is None:
                writer = self.buffer.block_writer
                if data:
                    if self.response_body.append(data, writer):
                        self.buffer.take_rejected_tail(self.ref)
                    else:
                        self.buffer.remember_rejected_tail(
                            self.ref, self.response_body.logical_size, data
                        )
                self.sse.feed(data, monotonic())

    def finish_sse(self, error: Exception | None = None) -> None:
        if self.sse is not None and self.streams_sse:
            with self.buffer.lock:
                if not self.buffer.closed:
                    writer = self.buffer.block_writer
                    tail = self.buffer.take_rejected_tail(self.ref)
                    if error is not None and tail is not None:
                        ranges = writer.append_critical(tail.data)
                        if ranges is not None:
                            self.response_body.retain_ranges(
                                tail.end - len(tail.data), ranges
                            )
                    self.sse.finish(monotonic(), _sse_ending(error))
                    if error is not None:
                        writer.flush()

    def normalization_started(self, *, enabled: bool) -> None:
        self.normalization_status = (
            TraceNormalizationStatus.UNCHANGED
            if enabled
            else TraceNormalizationStatus.SKIPPED
        )

    def normalization_rewrites(
        self, frame_index: int, changes: list[tuple[int, int, str]]
    ) -> None:
        with self.buffer.lock:
            if self.buffer.closed:
                return
            self.normalization_status = TraceNormalizationStatus.CORRECTED
            available = min(
                TRACE_MAX_NORMALIZATION_REWRITES - len(self.rewrites),
                self.buffer.normalization_remaining,
            )
            self.normalization_partial |= len(changes) > available
            self.buffer.normalization_remaining -= min(len(changes), available)
            self.rewrites.extend(
                TraceNormalizationRewrite(
                    choice_index=choice,
                    tool_index=tool,
                    tool_call_id=safe_identifier(original),
                    frame_index=frame_index,
                )
                for choice, tool, original in changes[:available]
            )

    def normalization(self, *, raw_stored: bool) -> TraceNormalization:
        # A CR at the end of a transport chunk can be observed by the
        # normalizer before the raw lane finishes recording its CRLF frame.
        lane = self.sse if raw_stored else None
        rewrites = [
            rewrite
            if (index := rewrite.frame_index) is not None
            and lane is not None
            and lane.has_persisted_frame(index)
            else rewrite.model_copy(update={"frame_index": None})
            for rewrite in self.rewrites
        ]
        return TraceNormalization(
            attempt_ref=self.ref,
            status=self.normalization_status,
            rewrites=rewrites,
            partial=self.normalization_partial
            or (
                self.normalization_status
                in (
                    TraceNormalizationStatus.UNCHANGED,
                    TraceNormalizationStatus.CORRECTED,
                )
                and self.sse is not None
                and self.sse.partial
            ),
        )

    def summary(
        self,
        release: str | None,
        *,
        stored: bool,
        observed_through_rank: int | None = None,
    ) -> TraceHttpAttempt:
        stage = None
        if self.status is None:
            stage = TraceHttpFailureStage.RESPONSE_HEADERS
        elif self.status >= 400:
            stage = TraceHttpFailureStage.HTTP_STATUS
        elif self.failed:
            stage = TraceHttpFailureStage.RESPONSE_BODY
        upstream = next(
            (
                value
                for key in _REQUEST_IDS
                if (value := safe_identifier(self.response_headers.get(key)))
            ),
            None,
        )
        complete = (
            self.request_complete
            and self.request_body.retained_complete()
            and (
                self.status is None
                or (self.response_complete and self.response_body.retained_complete())
            )
        )
        return TraceHttpAttempt(
            ref=self.ref,
            call_id=self.call_id,
            tool_ref=self.tool_ref,
            attempt=self.number,
            model=self.model,
            release=release,
            status=self.status,
            upstream_id=upstream,
            failure_stage=stage,
            duration_ms=min(
                _MAX_COUNT, int(((self.ended or monotonic()) - self.started) * 1000)
            ),
            request_bytes=self.request_body.observed,
            response_bytes=self.response_body.observed,
            observed_through_rank=observed_through_rank,
            completeness=(
                TraceHttpCompleteness.UNAVAILABLE
                if not stored
                else TraceHttpCompleteness.COMPLETE
                if complete
                else TraceHttpCompleteness.PARTIAL
            ),
        )


@dataclass(slots=True)
class HttpTurnBuffer:
    block_writer: TraceBlockWriter
    lock: LockType = field(default_factory=Lock)
    attempts: list[RecordedHttpAttempt] = field(default_factory=list)
    closed: bool = False
    incomplete: bool = False
    sse: SseClock = field(default_factory=SseClock)
    outgoing: RecordedSseLane | None = None
    model_calls: list[RecordedModelCall] = field(default_factory=list)
    normalization_remaining: int = _NORMALIZATION_REWRITES_PER_SEGMENT
    tool_calls: list[RecordedToolCall] = field(default_factory=list)
    tool_call_counts: dict[str | None, int] = field(default_factory=dict)
    discarded_drains: DiscardedResponseDrains | None = None
    discarded_pending: set[asyncio.Task[None]] = field(default_factory=set)
    snapshots: SnapshotWork | None = None
    _rejected_tails: OrderedDict[str, _RejectedProviderTail] = field(
        default_factory=OrderedDict
    )
    _rejected_tail_bytes: int = 0

    def take_rejected_tail(self, ref: str) -> _RejectedProviderTail | None:
        tail = self._rejected_tails.pop(ref, None)
        if tail is not None:
            self._rejected_tail_bytes -= len(tail.data)
        return tail

    def remember_rejected_tail(self, ref: str, end: int, data: bytes) -> None:
        previous = self.take_rejected_tail(ref)
        suffix = data[-TRACE_CRITICAL_TAIL_BYTES:]
        remaining = TRACE_CRITICAL_TAIL_BYTES - len(suffix)
        if previous is not None and previous.end == end - len(data) and remaining:
            suffix = previous.data[-remaining:] + suffix
        self._rejected_tails[ref] = _RejectedProviderTail(end, suffix)
        self._rejected_tail_bytes += len(suffix)
        while (
            self._rejected_tail_bytes > TRACE_CRITICAL_TAIL_BYTES
            or len(self._rejected_tails) > _MAX_PROVIDER_TAILS
        ):
            _, earlier = self._rejected_tails.popitem(last=False)
            self._rejected_tail_bytes -= len(earlier.data)

    def mark_failed_blocks(self, failed_blocks: frozenset[str]) -> None:
        if not failed_blocks:
            return
        self.incomplete = True
        for attempt in self.attempts:
            attempt.request_body.discard_failed_blocks(failed_blocks)
            attempt.response_body.discard_failed_blocks(failed_blocks)
        for model in self.model_calls:
            model.discard_failed_blocks(failed_blocks)
        for tool in self.tool_calls:
            tool.discard_failed_blocks(failed_blocks)

    async def snapshot_copy(
        self, copy: Callable[..., _Snapshot], *args: object
    ) -> _Snapshot | None:
        if self.snapshots is None:
            return copy(*args)
        snapshot = await self.snapshots.run(copy, *args)
        if snapshot is None:
            with self.lock:
                if not self.closed:
                    self.incomplete = True
        return snapshot

    async def settle_discarded_bodies(self) -> None:
        if self.discarded_pending:
            await asyncio.wait(self.discarded_pending)

    def start_tool(
        self, tool_name: str, call_id: str | None, source: TraceToolSource
    ) -> RecordedToolCall | None:
        with self.lock:
            if self.closed:
                return None
            name = safe_identifier(tool_name)
            attempt = 1 + self.tool_call_counts.get(name, 0)
            self.tool_call_counts[name] = attempt
            tool = RecordedToolCall(
                self, safe_identifier(call_id), name, source, attempt
            )
            self.tool_calls.append(tool)
            return tool

    def begin_http(
        self,
        request: httpx.Request | httpx2.Request,
        *,
        call_id: str,
        number: int,
        model: str | None = None,
        tool_ref: str | None = None,
    ) -> RecordedHttpAttempt | None:
        with self.lock:
            if self.closed:
                return None
            url = request.url
            path, query_separator, _ = url.raw_path.partition(b"?")
            authority = url.netloc.decode("ascii")
            target = f"{url.scheme}://{authority}{path.decode('ascii')}"
            bearer_replay = (
                tool_ref is None
                and len(target) <= 2048
                and not query_separator
                and not url.username
                and not url.password
                and _has_replayable_bearer_headers(request.headers, authority)
            )
            attempt = RecordedHttpAttempt(
                self,
                uuid4().hex,
                call_id,
                number,
                model,
                request.method[:16],
                target[:2048],
                _headers(request.headers, _REQUEST_HEADERS),
                tool_ref=tool_ref,
                bearer_replay=bearer_replay,
            )
            if tool_ref is None:
                attempt.sse = RecordedSseLane(
                    attempt.ref,
                    self.sse,
                    self.sse.at(attempt.started),
                    writer=self.block_writer,
                )
            self.attempts.append(attempt)
            try:
                data = request.content
            except (httpx.RequestNotRead, httpx2.RequestNotRead):
                return attempt
            attempt.request_body.count_transport(data)
            attempt.request_complete = True
            if not attempt.request_body.append(data, self.block_writer):
                self.incomplete = True
            return attempt

    def start_execution(self, started: float, offset_ms: int) -> None:
        self.sse.started = started
        self.sse.offset_ms = offset_ms

    def start_stream(
        self, headers_at: float, offset_ms: int, headers: dict[str, str] | None = None
    ) -> None:
        self.start_execution(headers_at, offset_ms)
        self.outgoing = RecordedSseLane(
            uuid4().hex,
            self.sse,
            offset_ms,
            headers_ms=offset_ms if headers is not None else None,
            headers=headers,
            writer=self.block_writer,
        )

    def emit(self, data: bytes, kind: str) -> None:
        with self.lock:
            if self.outgoing is not None and not self.closed:
                self.outgoing.emitted(data, kind, monotonic())

    def close(self) -> list[RecordedHttpAttempt]:
        with self.lock:
            self.closed = True
            now = monotonic()
            for attempt in self.attempts:
                if attempt.sse is not None:
                    attempt.sse.finish(now, TraceSseEnding.CLOSED)
            return self.attempts


@dataclass(slots=True)
class ModelHttpCapture:
    buffer: HttpTurnBuffer
    call_id: str
    model: str | None
    attempts: int = 0
    snapshot: RecordedModelCall | None = None

    def record_model_call(self) -> bool:
        with self.buffer.lock:
            if self.buffer.closed:
                return False
            self.snapshot = RecordedModelCall(self.call_id, self.model)
            self.buffer.model_calls.append(self.snapshot)
            return True

    async def input_snapshot(
        self, messages: Sequence[BaseMessage], tools: Sequence[object]
    ) -> None:
        await self._record_snapshot(messages, tools, input_=True)

    def note_snapshot_loss(self) -> None:
        with self.buffer.lock:
            if not self.buffer.closed:
                self.buffer.incomplete = True

    async def output_snapshot(
        self,
        messages: Sequence[BaseMessage],
        *,
        partial: bool,
        had_chunks: bool,
        partial_chunks: Sequence[ChatGenerationChunk],
    ) -> None:
        if not messages and not partial_chunks:
            with self.buffer.lock:
                if (
                    not self.buffer.closed
                    and self.snapshot is not None
                    and partial
                    and not had_chunks
                ):
                    self.snapshot.output_state = TraceModelOutputState.ABSENT
            return
        await self._record_snapshot(
            messages, (), partial=partial, partial_chunks=partial_chunks
        )

    async def _record_snapshot(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[object],
        *,
        input_: bool = False,
        partial: bool = False,
        partial_chunks: Sequence[ChatGenerationChunk] = (),
    ) -> None:
        call = self.snapshot
        writer = self.buffer.block_writer
        if call is None or self.buffer.closed:
            return
        try:
            retained = await self.buffer.snapshot_copy(
                stage_snapshot, messages, tools, partial_chunks, writer.value_capacity
            )
        except Exception:
            self.note_snapshot_loss()
            return
        with self.buffer.lock:
            if self.buffer.closed:
                return
            if retained is None:
                self.buffer.incomplete = True
                return
            snapshot, data = retained
            blocks = writer.append(data)
            if blocks is None:
                self.buffer.incomplete = True
                return
            self.buffer.incomplete |= snapshot.partial
            if input_:
                call.input = snapshot
                call.input_blocks = blocks
            else:
                call.output = snapshot
                call.output_blocks = blocks
                call.output_state = (
                    TraceModelOutputState.PARTIAL
                    if partial or snapshot.partial
                    else TraceModelOutputState.COMPLETE
                )

    def begin(self, request: HttpRequest) -> HttpAttempt | None:
        self.attempts += 1
        return self.buffer.begin_http(
            request, call_id=self.call_id, number=self.attempts, model=self.model
        )


class _BodyIndexPage(BaseModel):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]


class _BodyManifest(BaseModel):
    size: Annotated[int, Field(ge=0)]
    complete: bool
    decoded: bool = False
    index: list[_BodyIndexPage]


class _BodyPart(BaseModel):
    start: Annotated[int, Field(ge=0)]
    block_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    block_offset: Annotated[int, Field(ge=0, lt=TRACE_BLOCK_BYTES)]
    length: Annotated[int, Field(gt=0, le=TRACE_BLOCK_BYTES)]

    @property
    def end(self) -> int:
        return self.start + self.length


_BODY_PARTS = TypeAdapter(list[_BodyPart])


class _HttpManifest(BaseModel):
    version: Literal[2]
    attempt: TraceHttpAttempt | None = None
    method: str
    target: str
    bearer_replay: bool | None = None
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request: _BodyManifest
    response: _BodyManifest | None


class _ModelManifest(BaseModel):
    version: Literal[2]
    input_blocks: tuple[TraceBlockRange, ...] | None
    output_blocks: tuple[TraceBlockRange, ...] | None
    output_state: TraceModelOutputState
    normalization: list[TraceNormalization]


class _ToolManifest(BaseModel):
    version: Literal[2]
    input_blocks: tuple[TraceBlockRange, ...] | None
    output_blocks: tuple[TraceBlockRange, ...] | None
    result_model_ref: EvidenceReference | None
    call_id: str | None
    partial: bool


_TOOL_FIELD = TypeAdapter(object)


def _session_path(session_id: str) -> str:
    return f"conversation-traces/v1/{sha256(session_id.encode()).hexdigest()}"


ArtifactFiles = dict[str, bytes]


def artifact_size(files: ArtifactFiles) -> int:
    """Count exact stored payload bytes; virtual directory markers cost zero bytes."""
    return sum(len(data) for data in files.values())


async def _finish_storage_call(
    operation: Coroutine[object, object, None], deadline: float | None
) -> None:
    """Keep an already-started object request owned until the backend call settles."""
    if deadline is None:
        await operation
        return
    if deadline <= monotonic():
        operation.close()
        raise TimeoutError("trace write deadline exceeded")
    # Filesystems use synchronous SDKs in a thread. Cancelling the await would
    # let the PUT continue outside the reservation, possibly after cleanup.
    await operation
    if deadline <= monotonic():
        raise TimeoutError("trace write deadline exceeded")


class TraceHttpArtifactStore:
    def __init__(self, filesystem: BaseFilesystem | TraceObjectIO) -> None:
        self._filesystem = filesystem

    async def close(self) -> None:
        if isinstance(self._filesystem, TraceObjectIO):
            await self._filesystem.close()

    async def _read_object(self, path: str) -> bytes:
        deadline = storage_deadline.get()
        if deadline is not None and deadline <= monotonic():
            raise TimeoutError("trace read deadline exceeded")
        return await self._filesystem.read(path)

    async def _read_model_artifact(self, session_id: str, ref: str) -> _ModelManifest:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/{_MODEL_MANIFEST_FILE}")
        if len(data) > _SNAPSHOT_MANIFEST_MAX_BYTES:
            raise ValueError("Oversized model trace artifact")
        return _ModelManifest.model_validate_json(data)

    async def _read_model_snapshot(
        self, session_id: str, ranges: tuple[TraceBlockRange, ...] | None
    ) -> TraceModelSnapshot | None:
        if ranges is None:
            return None
        return TraceModelSnapshot.model_validate_json(
            await self.read_block_ranges(
                session_id, ranges, max_bytes=TRACE_WRITER_QUEUE_BYTES
            )
        )

    async def read_model(self, session_id: str, ref: str) -> TraceModelEvidence:
        manifest = await self._read_model_artifact(session_id, ref)
        input_, output = await asyncio.gather(
            self._read_model_snapshot(session_id, manifest.input_blocks),
            self._read_model_snapshot(session_id, manifest.output_blocks),
        )
        return TraceModelEvidence(
            input=input_,
            output=output,
            output_state=manifest.output_state,
            normalization=manifest.normalization,
        )

    @staticmethod
    def model_files(
        call: RecordedModelCall, evidence: TraceModelEvidence
    ) -> ArtifactFiles:
        artifact = _ModelManifest(
            version=2,
            input_blocks=call.input_blocks,
            output_blocks=call.output_blocks,
            output_state=evidence.output_state,
            normalization=evidence.normalization,
        )
        return {_MODEL_MANIFEST_FILE: artifact.model_dump_json().encode()}

    async def read_tool(self, session_id: str, ref: str) -> TraceToolEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/{_TOOL_MANIFEST_FILE}")
        if len(data) > _SNAPSHOT_MANIFEST_MAX_BYTES:
            raise ValueError("Oversized tool trace artifact")
        manifest = _ToolManifest.model_validate_json(data)
        input_, output, result = await asyncio.gather(
            self._read_tool_field(session_id, manifest.input_blocks),
            self._read_tool_field(session_id, manifest.output_blocks),
            self._read_tool_result(session_id, manifest),
        )
        return TraceToolEvidence(
            input=input_,
            output=output,
            model_result=result[0],
            partial=manifest.partial or result[1],
        )

    async def _read_tool_field(
        self, session_id: str, ranges: tuple[TraceBlockRange, ...] | None
    ) -> object:
        if ranges is None:
            return None
        return _TOOL_FIELD.validate_json(
            await self.read_block_ranges(
                session_id, ranges, max_bytes=TRACE_WRITER_QUEUE_BYTES
            )
        )

    async def _read_tool_result(
        self, session_id: str, manifest: _ToolManifest
    ) -> tuple[dict[str, object] | None, bool]:
        if manifest.call_id is None or manifest.result_model_ref is None:
            return None, False
        try:
            related = await self._read_model_artifact(
                session_id, manifest.result_model_ref
            )
            snapshot = await self._read_model_snapshot(session_id, related.input_blocks)
        except FileNotFoundError:
            return None, True
        if snapshot is not None:
            for message in reversed(snapshot.messages):
                if message.get("tool_call_id") == manifest.call_id:
                    return message, False
        return None, True

    @staticmethod
    def tool_files(tool: RecordedToolCall) -> ArtifactFiles:
        artifact = _ToolManifest(
            version=2,
            input_blocks=tool.input_blocks,
            output_blocks=tool.output_blocks,
            result_model_ref=tool.result_model_ref,
            call_id=tool.call_id,
            partial=tool.partial,
        )
        return {_TOOL_MANIFEST_FILE: artifact.model_dump_json().encode()}

    async def write(self, session_id: str, attempt: RecordedHttpAttempt) -> None:
        await self.publish(session_id, attempt.ref, self.http_files(attempt))

    @staticmethod
    def http_files(attempt: RecordedHttpAttempt) -> ArtifactFiles:
        """Describe the exact HTTP chunk and manifest bytes without copying the bodies."""
        files: ArtifactFiles = {}
        request = _plan_body(
            files, "request", attempt.request_body, attempt.request_complete
        )
        response = (
            _plan_body(
                files,
                "response",
                attempt.response_body,
                attempt.response_complete,
                decoded=attempt.streams_sse
                and attempt.response_headers.get("content-encoding", "identity")
                != "identity",
            )
            if attempt.status is not None
            else None
        )
        manifest = _HttpManifest(
            version=2,
            attempt=attempt.summary(None, stored=True),
            method=attempt.method,
            target=attempt.target,
            bearer_replay=attempt.bearer_replay,
            request_headers=attempt.request_headers,
            response_headers=attempt.response_headers,
            request=request,
            response=response,
        )
        files["manifest.json"] = manifest.model_dump_json().encode()
        return files

    async def publish(
        self,
        session_id: str,
        ref: str,
        files: ArtifactFiles,
        *,
        create_prefix: bool = True,
        deadline: float | None = None,
    ) -> None:
        """Write one reserved opaque evidence prefix, stopping before the next PUT on timeout."""
        prefix = f"{_session_path(session_id)}/{ref}"
        token = storage_deadline.set(deadline)
        try:
            if create_prefix:
                await _finish_storage_call(self._filesystem.mkdir(prefix), deadline)
            for name, data in files.items():
                await _finish_storage_call(
                    self._filesystem.write(f"{prefix}/{name}", data), deadline
                )
        finally:
            storage_deadline.reset(token)

    async def _http_manifest(self, session_id: str, ref: str) -> _HttpManifest:
        prefix = f"{_session_path(session_id)}/{ref}"
        manifest = _HttpManifest.model_validate_json(
            await self._read_object(f"{prefix}/manifest.json")
        )
        if manifest.attempt is not None and manifest.attempt.ref != ref:
            raise ValueError("HTTP trace manifest reference mismatch")
        return manifest

    async def read(
        self,
        session_id: str,
        ref: str,
        request_offset: int = 0,
        response_offset: int = 0,
    ) -> TraceHttpEvidence:
        manifest = await self._http_manifest(session_id, ref)
        request = await self._read_http_body(
            session_id, ref, "request", manifest.request, request_offset
        )
        response = (
            await self._read_http_body(
                session_id, ref, "response", manifest.response, response_offset
            )
            if manifest.response is not None
            else None
        )
        return TraceHttpEvidence(
            method=manifest.method,
            target=manifest.target,
            bearer_replay=manifest.bearer_replay,
            request_headers=manifest.request_headers,
            response_headers=manifest.response_headers,
            request_body=request,
            response_body=response,
        )

    async def _read_http_body(
        self,
        session_id: str,
        ref: str,
        side: str,
        manifest: _BodyManifest,
        offset: int,
    ) -> TraceHttpBody:
        if offset < 0 or offset > manifest.size:
            raise ValueError("Invalid trace body offset")
        prefix = f"{_session_path(session_id)}/{ref}"
        page = bisect_right(manifest.index, offset, key=lambda item: item.end)
        if page == len(manifest.index):
            start, data, next_offset = offset, b"", None
        else:
            parts = await self._read_body_index(prefix, side, manifest, page)
            start, ranges, next_offset = _plan_body_page(
                parts, offset, TRACE_BLOCK_BYTES
            )
            if next_offset is None and page + 1 < len(manifest.index):
                next_offset = manifest.index[page + 1].start
            data = await self.read_block_ranges(session_id, ranges)
        return TraceHttpBody(
            data=b64encode(data).decode("ascii"),
            complete=manifest.complete,
            decoded=manifest.decoded,
            total_bytes=manifest.size,
            offset=start,
            next_offset=next_offset,
        )

    async def _read_body_index(
        self, prefix: str, side: str, manifest: _BodyManifest, page: int
    ) -> list[_BodyPart]:
        compressed = await self._read_object(f"{prefix}/{side}-index-{page}.zst")
        payload = await asyncio.to_thread(decode_trace_block, compressed)
        parts = _BODY_PARTS.validate_json(payload)
        directory = manifest.index[page]
        if (
            not parts
            or len(parts) > _HTTP_BODY_INDEX_SPANS
            or parts[0].start != directory.start
            or parts[-1].end != directory.end
            or directory.end > manifest.size
            or any(part.end > following.start for part, following in pairwise(parts))
        ):
            raise ValueError("Invalid HTTP trace body index")
        return parts

    async def read_body_range(
        self, session_id: str, ref: str, offset: int, size: int
    ) -> bytes:
        """Read exact original SSE bytes from their shared HTTP response archive."""
        if not 0 < size <= TRACE_BLOCK_BYTES or offset < 0:
            raise ValueError("Invalid trace body range")
        manifest = (await self._http_manifest(session_id, ref)).response
        if manifest is None or offset + size > manifest.size:
            raise FileNotFoundError("Trace response range is unavailable")
        prefix = f"{_session_path(session_id)}/{ref}"
        page = bisect_right(manifest.index, offset, key=lambda item: item.end)
        cursor = offset
        end = offset + size
        ranges: list[TraceBlockRange] = []
        while cursor < end and page < len(manifest.index):
            parts = await self._read_body_index(prefix, "response", manifest, page)
            start, scoped_ranges, _ = _plan_body_page(
                parts, cursor, end - cursor, bound_fetches=False
            )
            if start != cursor:
                break
            ranges.extend(scoped_ranges)
            cursor += sum(part.length for part in scoped_ranges)
            page += 1
        if cursor != end:
            raise FileNotFoundError("Trace response range is unavailable")
        return await self.read_block_ranges(session_id, ranges)

    async def response_coverage(
        self, session_id: str, ref: str, start: int, end: int
    ) -> list[tuple[int, int]]:
        """Return recorded logical ranges for a paged provider response window."""
        response = (await self._http_manifest(session_id, ref)).response
        if response is None:
            return []
        prefix = f"{_session_path(session_id)}/{ref}"
        page = bisect_right(response.index, start, key=lambda item: item.end)
        intervals: list[tuple[int, int]] = []
        while page < len(response.index) and response.index[page].start < end:
            for part in await self._read_body_index(prefix, "response", response, page):
                left, right = max(start, part.start), min(end, part.end)
                if left >= right:
                    continue
                if intervals and intervals[-1][1] == left:
                    intervals[-1] = (intervals[-1][0], right)
                else:
                    intervals.append((left, right))
            page += 1
        return intervals

    async def read_block_ranges(
        self,
        session_id: str,
        ranges: Sequence[TraceBlockRange],
        *,
        max_bytes: int = TRACE_BLOCK_BYTES,
    ) -> bytes:
        if sum(part.length for part in ranges) > max_bytes:
            raise ValueError("Oversized trace block read")
        prefix = _session_path(session_id)
        body = bytearray()
        block_id = ""
        block = b""
        for part in ranges:
            if (
                _BLOCK_ID.fullmatch(part.block_id) is None
                or part.offset < 0
                or not 0 < part.length <= TRACE_BLOCK_BYTES
                or part.offset + part.length > TRACE_BLOCK_BYTES
            ):
                raise ValueError("Invalid trace block range")
            if part.block_id != block_id:
                encoded = await self._read_object(
                    f"{prefix}/{part.block_id}/{TRACE_BLOCK_FILE}"
                )
                block = await asyncio.to_thread(decode_trace_block, encoded)
                block_id = part.block_id
            end = part.offset + part.length
            if end > len(block):
                raise ValueError("Trace block range exceeds its payload")
            body.extend(block[part.offset : end])
        return bytes(body)

    async def erase(self, session_id: str, ref: str | None = None) -> None:
        path = _session_path(session_id)
        path = f"{path}/{ref}" if ref is not None else path
        if isinstance(self._filesystem, TraceObjectIO):
            await self._filesystem.erase(path)
        else:
            await self._filesystem.delete(path)

    async def measure(self, session_id: str, ref: str) -> int:
        """Count physically retained bytes under an evidence prefix."""
        path = f"{_session_path(session_id)}/{ref}"
        if isinstance(self._filesystem, TraceObjectIO):
            return await self._filesystem.measure(path)
        resources = await self._filesystem.list(path)
        return sum(resource.size or 0 for resource in resources if resource.is_file())

    @staticmethod
    def sse_files(lane: RecordedSseLane) -> ArtifactFiles:
        files: ArtifactFiles = (
            {"sse-pages-v2.json": lane.page_manifest()}
            if lane.frame_count or lane.headers is not None
            else {}
        )
        if lane.headers is not None:
            files["sse-headers.json"] = (
                TraceSseHeaders(headers=lane.headers).model_dump_json().encode()
            )
        return files

    async def read_sse_headers(self, session_id: str, ref: str) -> TraceSseHeaders:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/sse-headers.json")
        if len(data) > TRACE_HTTP_CHUNK_BYTES:
            raise ValueError("Oversized SSE headers")
        return TraceSseHeaders.model_validate_json(data)

    async def read_sse_page_manifest(
        self, session_id: str, ref: str
    ) -> SsePageManifest:
        prefix = f"{_session_path(session_id)}/{ref}"
        return SsePageManifest.model_validate_json(
            await self._read_object(f"{prefix}/sse-pages-v2.json")
        )


def _plan_body(
    files: ArtifactFiles,
    side: str,
    body: _Body,
    complete: bool,
    *,
    decoded: bool = False,
) -> _BodyManifest:
    index: list[_BodyIndexPage] = []
    for start in range(0, len(body.spans), _HTTP_BODY_INDEX_SPANS):
        spans = body.spans[start : start + _HTTP_BODY_INDEX_SPANS]
        payload = _BODY_PARTS.dump_json(
            [
                _BodyPart(
                    start=part.start,
                    block_id=part.block_id,
                    block_offset=part.block_offset,
                    length=part.length,
                )
                for part in spans
            ]
        )
        files[f"{side}-index-{len(index)}.zst"] = encode_trace_block(payload)
        index.append(_BodyIndexPage(start=spans[0].start, end=spans[-1].end))
    return _BodyManifest(
        size=body.logical_size,
        complete=complete and body.retained_complete(),
        decoded=decoded,
        index=index,
    )


def _plan_body_page(
    parts: list[_BodyPart],
    offset: int,
    length: int,
    *,
    bound_fetches: bool = True,
) -> tuple[int, list[TraceBlockRange], int | None]:
    """Page over a contiguous range. A subsequent page can begin beyond a gap."""
    first = bisect_right(parts, offset, key=lambda part: part.end)
    if first == len(parts):
        return offset, [], None
    start = cursor = max(offset, parts[first].start)
    end = start + length
    ranges: list[TraceBlockRange] = []
    blocks: set[str] = set()
    for part in islice(parts, first, None):
        if (
            cursor == end
            or part.start > cursor
            or (
                bound_fetches
                and part.block_id not in blocks
                and len(blocks) == _HTTP_BODY_PAGE_BLOCKS
            )
        ):
            return start, ranges, max(cursor, part.start)
        blocks.add(part.block_id)
        until = min(end, part.end)
        ranges.append(
            TraceBlockRange(
                part.block_id, part.block_offset + cursor - part.start, until - cursor
            )
        )
        cursor = until
        if until < part.end:
            return start, ranges, cursor
    return start, ranges, None
