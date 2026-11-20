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
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Sequence
from contextvars import Context
from dataclasses import dataclass, field
from hashlib import sha256
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
    TRACE_HTTP_TURN_BYTES,
    TRACE_MAX_HTTP_ATTEMPTS,
    TRACE_MAX_MODEL_CALLS,
    TRACE_MAX_NORMALIZATION_REWRITES,
    TRACE_MAX_SSE_FRAMES,
    TRACE_MAX_TOOL_CALLS,
    TraceHttpAttempt,
    TraceHttpBody,
    TraceHttpCompleteness,
    TraceHttpEvidence,
    TraceHttpFailureStage,
    TraceModelEvidence,
    TraceModelOutputState,
    TraceNormalization,
    TraceNormalizationRewrite,
    TraceNormalizationStatus,
    TraceSseEnding,
    TraceSseFrame,
    TraceSseHeaders,
    TraceToolEvidence,
    TraceToolSource,
)
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.model.http_capture import HttpAttempt, HttpRequest
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic import BaseModel, Field

from fred_runtime.app.conversation_trace_model import (
    MODEL_SNAPSHOT_BYTES,
    MODEL_TURN_BYTES,
    RecordedModelCall,
    SnapshotWork,
    capture_snapshot,
)
from fred_runtime.app.conversation_trace_sse import RecordedSseLane, SseBudget
from fred_runtime.app.conversation_trace_storage import TraceObjectIO, storage_deadline
from fred_runtime.app.conversation_trace_tools import TOOL_TURN_BYTES, RecordedToolCall

_MAX_COUNT = 2**31 - 1
_MAX_CHUNKS = TRACE_HTTP_TURN_BYTES // TRACE_HTTP_CHUNK_BYTES
_MAX_DISCARDED_BODIES = 8
_MAX_DISCARDED_PER_SEGMENT = 2
_Snapshot = TypeVar("_Snapshot")
_NORMALIZATION_REWRITES_PER_SEGMENT = 128
_IDENT = re.compile(r"[a-zA-Z0-9_.:-]{1,255}\Z")
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
class _Body:
    chunks: list[bytearray] = field(default_factory=list)
    size: int = 0
    observed: int = 0

    def add(self, data: bytes, budget: int) -> int:
        self.observed = min(_MAX_COUNT, self.observed + len(data))
        remaining = min(budget, len(data))
        kept = remaining
        if remaining:
            view = memoryview(data)
            offset = 0
            while remaining:
                if not self.chunks or len(self.chunks[-1]) == TRACE_HTTP_CHUNK_BYTES:
                    self.chunks.append(bytearray())
                chunk = self.chunks[-1]
                count = min(TRACE_HTTP_CHUNK_BYTES - len(chunk), remaining)
                chunk.extend(view[offset : offset + count])
                offset += count
                remaining -= count
            self.size += kept
        return kept


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
            return (
                self.buffer.remaining
                if not self.buffer.closed or self.draining_discarded_body
                else 0
            )

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
                self.buffer.remaining -= self.response_body.add(
                    data, self.buffer.remaining
                )

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
                self.sse.feed(data, monotonic())

    def finish_sse(self, error: Exception | None = None) -> None:
        if self.sse is not None and self.streams_sse:
            with self.buffer.lock:
                if not self.buffer.closed:
                    self.sse.finish(monotonic(), _sse_ending(error))

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
                    frame_index=frame_index
                    if frame_index < TRACE_MAX_SSE_FRAMES
                    else None,
                )
                for choice, tool, original in changes[:available]
            )

    def normalization(self, *, raw_stored: bool) -> TraceNormalization:
        # A CR at the end of a transport chunk can be observed by the
        # normalizer before the raw lane finishes recording its CRLF frame.
        frames = self.sse.frames if self.sse is not None and raw_stored else []
        rewrites = [
            rewrite
            if (index := rewrite.frame_index) is not None
            and index < len(frames)
            and frames[index].offset is not None
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
        complete = self.request_complete and (
            self.status is None or self.response_complete
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
                if complete and self.response_body.size == self.response_body.observed
                else TraceHttpCompleteness.PARTIAL
            ),
        )


@dataclass(slots=True)
class HttpTurnBuffer:
    lock: LockType = field(default_factory=Lock)
    attempts: list[RecordedHttpAttempt] = field(default_factory=list)
    remaining: int = TRACE_HTTP_TURN_BYTES
    closed: bool = False
    incomplete: bool = False
    sse: SseBudget = field(default_factory=SseBudget)
    outgoing: RecordedSseLane | None = None
    model_calls: list[RecordedModelCall] = field(default_factory=list)
    model_remaining: int = MODEL_TURN_BYTES
    normalization_remaining: int = _NORMALIZATION_REWRITES_PER_SEGMENT
    tool_calls: list[RecordedToolCall] = field(default_factory=list)
    tool_remaining: int = TOOL_TURN_BYTES
    discarded_drains: DiscardedResponseDrains | None = None
    discarded_pending: set[asyncio.Task[None]] = field(default_factory=set)
    snapshots: SnapshotWork | None = None

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
            if self.closed or len(self.tool_calls) >= TRACE_MAX_TOOL_CALLS:
                self.incomplete = True
                return None
            name = safe_identifier(tool_name)
            attempt = 1 + sum(call.tool_name == name for call in self.tool_calls)
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
            if len(self.attempts) >= TRACE_MAX_HTTP_ATTEMPTS:
                self.incomplete = True
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
                    attempt.ref, self.sse, self.sse.at(attempt.started)
                )
            self.attempts.append(attempt)
            try:
                data = request.content
            except (httpx.RequestNotRead, httpx2.RequestNotRead):
                return attempt
            kept = attempt.request_body.add(data, self.remaining)
            self.remaining -= kept
            attempt.request_complete = kept == len(data)
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
            if (
                self.buffer.closed
                or len(self.buffer.model_calls) >= TRACE_MAX_MODEL_CALLS
            ):
                self.buffer.incomplete = True
                return False
            self.snapshot = RecordedModelCall(self.call_id, self.model)
            self.buffer.model_calls.append(self.snapshot)
            return True

    async def input_snapshot(
        self, messages: Sequence[BaseMessage], tools: Sequence[object]
    ) -> None:
        await self._record_snapshot(messages, tools, input_=True)

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
        with self.buffer.lock:
            budget = min(self.buffer.model_remaining, MODEL_SNAPSHOT_BYTES)
            if self.buffer.closed or call is None or budget < 256:
                return
            self.buffer.model_remaining -= budget

        actual = 0
        try:
            copied = await self.buffer.snapshot_copy(
                capture_snapshot, messages, tools, budget, partial_chunks
            )
            if copied is None:
                return
            snapshot, size = copied
            with self.buffer.lock:
                if self.buffer.closed or snapshot is None:
                    return
                actual = size
                if input_:
                    call.input = snapshot
                else:
                    call.output = snapshot
                    call.output_state = (
                        TraceModelOutputState.PARTIAL
                        if partial or snapshot.partial
                        else TraceModelOutputState.COMPLETE
                    )
        finally:
            with self.buffer.lock:
                self.buffer.model_remaining += budget - actual

    def begin(self, request: HttpRequest) -> HttpAttempt | None:
        self.attempts += 1
        return self.buffer.begin_http(
            request, call_id=self.call_id, number=self.attempts, model=self.model
        )


class _BodyManifest(BaseModel):
    chunks: Annotated[int, Field(ge=0, le=_MAX_CHUNKS)]
    size: Annotated[int, Field(ge=0, le=TRACE_HTTP_TURN_BYTES)]
    complete: bool


class _HttpManifest(BaseModel):
    version: Literal[1] = 1
    attempt: TraceHttpAttempt | None = None
    method: str
    target: str
    bearer_replay: bool | None = None
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request: _BodyManifest
    response: _BodyManifest | None


def _session_path(session_id: str) -> str:
    return f"conversation-traces/v1/{sha256(session_id.encode()).hexdigest()}"


ArtifactFiles = dict[str, bytes | memoryview]


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

    async def read_model(self, session_id: str, ref: str) -> TraceModelEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/model-v1.json")
        if len(data) > MODEL_TURN_BYTES:
            raise ValueError("Oversized model trace artifact")
        return TraceModelEvidence.model_validate_json(data)

    async def write_tool(
        self, session_id: str, ref: str, evidence: TraceToolEvidence
    ) -> None:
        await self.publish(
            session_id, ref, {"tool-v1.json": evidence.model_dump_json().encode()}
        )

    async def read_tool(self, session_id: str, ref: str) -> TraceToolEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/tool-v1.json")
        if len(data) > TOOL_TURN_BYTES:
            raise ValueError("Oversized tool trace artifact")
        return TraceToolEvidence.model_validate_json(data)

    async def write(self, session_id: str, attempt: RecordedHttpAttempt) -> None:
        await self.publish(session_id, attempt.ref, self.http_files(attempt))

    @staticmethod
    def http_files(attempt: RecordedHttpAttempt) -> ArtifactFiles:
        """Describe the exact HTTP chunk and manifest bytes without copying the bodies."""
        files: ArtifactFiles = {}
        request = _plan_body(
            files, "request", attempt.request_body, attempt.request_complete
        )
        response = None
        if attempt.status is not None:
            response = _plan_body(
                files, "response", attempt.response_body, attempt.response_complete
            )
        manifest = _HttpManifest(
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
                    self._filesystem.write(f"{prefix}/{name}", bytes(data)), deadline
                )
        finally:
            storage_deadline.reset(token)

    async def read(self, session_id: str, ref: str) -> TraceHttpEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        manifest = _HttpManifest.model_validate_json(
            await self._read_object(f"{prefix}/manifest.json")
        )
        if manifest.attempt is not None and manifest.attempt.ref != ref:
            raise ValueError("HTTP trace manifest reference mismatch")
        request = await self._read_body(prefix, "request", manifest.request)
        response = (
            await self._read_body(prefix, "response", manifest.response)
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

    async def _read_body(
        self, prefix: str, side: str, manifest: _BodyManifest
    ) -> TraceHttpBody:
        body = bytearray()
        for index in range(manifest.chunks):
            chunk = await self._read_object(f"{prefix}/{side}-{index}")
            if (
                len(chunk) > TRACE_HTTP_CHUNK_BYTES
                or len(body) + len(chunk) > manifest.size
            ):
                raise ValueError("Invalid HTTP trace chunk size")
            body.extend(chunk)
        if len(body) != manifest.size:
            raise ValueError("Incomplete HTTP trace artifact")
        return TraceHttpBody(
            data=b64encode(body).decode("ascii"), complete=manifest.complete
        )

    async def erase(self, session_id: str, ref: str | None = None) -> None:
        path = _session_path(session_id)
        path = f"{path}/{ref}" if ref is not None else path
        if isinstance(self._filesystem, TraceObjectIO):
            await self._filesystem.erase(path)
        else:
            await self._filesystem.delete(path)

    async def measure(self, session_id: str, ref: str) -> int:
        """Count physically retained bytes under a legacy evidence prefix."""
        path = f"{_session_path(session_id)}/{ref}"
        if isinstance(self._filesystem, TraceObjectIO):
            return await self._filesystem.measure(path)
        resources = await self._filesystem.list(path)
        return sum(resource.size or 0 for resource in resources if resource.is_file())

    @staticmethod
    def sse_files(lane: RecordedSseLane) -> ArtifactFiles:
        """Describe bounded raw SSE chunks using views over the closed stream buffer."""
        data = memoryview(lane.raw)
        files: ArtifactFiles = {
            f"sse-{index}": data[start : start + TRACE_HTTP_CHUNK_BYTES]
            for index, start in enumerate(range(0, len(data), TRACE_HTTP_CHUNK_BYTES))
        }
        if lane.headers is not None:
            files["sse-headers.json"] = (
                TraceSseHeaders(headers=lane.headers).model_dump_json().encode()
            )
        return files

    async def write_sse(
        self, session_id: str, lane: RecordedSseLane, *, create_prefix: bool
    ) -> None:
        files = self.sse_files(lane)
        if files:
            await self.publish(session_id, lane.ref, files, create_prefix=create_prefix)

    async def read_sse_headers(self, session_id: str, ref: str) -> TraceSseHeaders:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._read_object(f"{prefix}/sse-headers.json")
        if len(data) > TRACE_HTTP_CHUNK_BYTES:
            raise ValueError("Oversized SSE headers")
        return TraceSseHeaders.model_validate_json(data)

    async def read_sse(
        self, session_id: str, ref: str, offset: int, size: int
    ) -> TraceSseFrame:
        prefix = f"{_session_path(session_id)}/{ref}"
        start, end = offset, offset + size
        data = bytearray()
        for index in range(
            start // TRACE_HTTP_CHUNK_BYTES, (end - 1) // TRACE_HTTP_CHUNK_BYTES + 1
        ):
            chunk = await self._read_object(f"{prefix}/sse-{index}")
            base = index * TRACE_HTTP_CHUNK_BYTES
            data.extend(chunk[max(0, start - base) : end - base])
        if len(data) != size:
            raise ValueError("Incomplete SSE frame")
        return TraceSseFrame(data=b64encode(data).decode("ascii"))


def _plan_body(
    files: ArtifactFiles, side: str, body: _Body, complete: bool
) -> _BodyManifest:
    """Add the recorded body chunks and return the format-independent sizes."""
    files.update(
        {
            f"{side}-{index}": memoryview(chunk)
            for index, chunk in enumerate(body.chunks)
        }
    )
    return _BodyManifest(
        chunks=len(body.chunks),
        size=body.size,
        complete=complete and body.size == body.observed,
    )
