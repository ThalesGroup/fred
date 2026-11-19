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

import re
from _thread import LockType
from base64 import b64encode
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

import httpx
import httpx2
from fred_core.conversation_trace import (
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
    TraceToolEvidence,
    TraceToolSource,
)
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.model.http_capture import HttpAttempt
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from fred_runtime.app.conversation_trace_model import (
    MODEL_TURN_BYTES,
    RecordedModelCall,
    capture_snapshot,
)
from fred_runtime.app.conversation_trace_sse import RecordedSseLane, SseBudget
from fred_runtime.app.conversation_trace_tools import TOOL_TURN_BYTES, RecordedToolCall

_MAX_COUNT = 2**31 - 1
_MAX_CHUNKS = TRACE_HTTP_TURN_BYTES // TRACE_HTTP_CHUNK_BYTES
_NORMALIZATION_REWRITES_PER_SEGMENT = 128
_IDENT = re.compile(r"[a-zA-Z0-9_.:-]{1,255}\Z")
_REQUEST_HEADERS = frozenset(
    {"accept", "content-type", "content-encoding", "content-length"}
)
_REQUEST_IDS = (
    "x-request-id",
    "apim-request-id",
    "x-correlation-id",
    "request-id",
    "x-amzn-requestid",
)
_RESPONSE_HEADERS = _REQUEST_HEADERS.union(_REQUEST_IDS, {"retry-after", "date"})


def _headers(
    source: httpx.Headers | httpx2.Headers, allow: frozenset[str]
) -> dict[str, str]:
    return {name: source[name][:256] for name in allow if name in source}


def safe_identifier(value: str | None) -> str | None:
    return value if value and _IDENT.fullmatch(value) else None


def _sse_ending(error: Exception | None) -> TraceSseEnding:
    if isinstance(error, httpx.TimeoutException):
        return TraceSseEnding.TIMEOUT
    if isinstance(error, httpx.RemoteProtocolError):
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
    normalization_status: TraceNormalizationStatus = (
        TraceNormalizationStatus.UNAVAILABLE
    )
    rewrites: list[TraceNormalizationRewrite] = field(default_factory=list)
    normalization_partial: bool = False

    @property
    def remaining_budget(self) -> int:
        with self.buffer.lock:
            return 0 if self.buffer.closed else self.buffer.remaining

    def headers(self, response: httpx.Response | httpx2.Response) -> None:
        self.status = response.status_code
        self.response_headers = _headers(response.headers, _RESPONSE_HEADERS)
        if not response.is_success or (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "text/event-stream"
        ):
            self.normalization_status = TraceNormalizationStatus.SKIPPED
        if self.sse is not None:
            self.sse.headers_ms = self.buffer.sse.at(monotonic())
            self.streams_sse = response.is_success and (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
                == "text/event-stream"
            )

    def chunk(self, data: bytes) -> None:
        with self.buffer.lock:
            if not self.buffer.closed:
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
            target = f"{url.scheme}://{url.netloc.decode('ascii')}{url.path}"[:2048]
            attempt = RecordedHttpAttempt(
                self,
                uuid4().hex,
                call_id,
                number,
                model,
                request.method[:16],
                target,
                _headers(request.headers, _REQUEST_HEADERS),
                tool_ref=tool_ref,
            )
            if tool_ref is None and self.outgoing is not None:
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

    def start_stream(self, headers_at: float, offset_ms: int) -> None:
        self.sse.started = headers_at
        self.sse.offset_ms = offset_ms
        self.outgoing = RecordedSseLane(
            uuid4().hex, self.sse, offset_ms, headers_ms=offset_ms
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

    def input_snapshot(
        self, messages: Sequence[BaseMessage], tools: Sequence[object]
    ) -> None:
        with self.buffer.lock:
            if self.buffer.closed or self.snapshot is None:
                return
            snapshot, size = capture_snapshot(
                messages, tools, self.buffer.model_remaining
            )
            self.snapshot.input = snapshot
            self.buffer.model_remaining -= size

    def output_snapshot(
        self, messages: Sequence[BaseMessage], *, partial: bool, had_chunks: bool
    ) -> None:
        with self.buffer.lock:
            if self.buffer.closed or self.snapshot is None:
                return
            if not messages:
                if partial and not had_chunks:
                    self.snapshot.output_state = TraceModelOutputState.ABSENT
                return
            snapshot, size = capture_snapshot(messages, (), self.buffer.model_remaining)
            self.snapshot.output = snapshot
            self.buffer.model_remaining -= size
            if snapshot is not None:
                self.snapshot.output_state = (
                    TraceModelOutputState.PARTIAL
                    if partial or snapshot.partial
                    else TraceModelOutputState.COMPLETE
                )

    def begin(self, request: httpx.Request) -> HttpAttempt | None:
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
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request: _BodyManifest
    response: _BodyManifest | None


def _session_path(session_id: str) -> str:
    return f"conversation-traces/v1/{sha256(session_id.encode()).hexdigest()}"


class TraceHttpArtifactStore:
    def __init__(self, filesystem: BaseFilesystem) -> None:
        self._filesystem = filesystem

    async def write_model(
        self, session_id: str, ref: str, evidence: TraceModelEvidence
    ) -> None:
        prefix = f"{_session_path(session_id)}/{ref}"
        await self._filesystem.mkdir(prefix)
        await self._filesystem.write(
            f"{prefix}/model-v1.json", evidence.model_dump_json()
        )

    async def read_model(self, session_id: str, ref: str) -> TraceModelEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._filesystem.read(f"{prefix}/model-v1.json")
        if len(data) > MODEL_TURN_BYTES:
            raise ValueError("Oversized model trace artifact")
        return TraceModelEvidence.model_validate_json(data)

    async def write_tool(
        self, session_id: str, ref: str, evidence: TraceToolEvidence
    ) -> None:
        prefix = f"{_session_path(session_id)}/{ref}"
        await self._filesystem.mkdir(prefix)
        await self._filesystem.write(
            f"{prefix}/tool-v1.json", evidence.model_dump_json()
        )

    async def read_tool(self, session_id: str, ref: str) -> TraceToolEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        data = await self._filesystem.read(f"{prefix}/tool-v1.json")
        if len(data) > TOOL_TURN_BYTES:
            raise ValueError("Oversized tool trace artifact")
        return TraceToolEvidence.model_validate_json(data)

    async def write(self, session_id: str, attempt: RecordedHttpAttempt) -> None:
        prefix = f"{_session_path(session_id)}/{attempt.ref}"
        await self._filesystem.mkdir(prefix)
        request = await self._write_body(
            prefix, "request", attempt.request_body, attempt.request_complete
        )
        response = None
        if attempt.status is not None:
            response = await self._write_body(
                prefix, "response", attempt.response_body, attempt.response_complete
            )
        manifest = _HttpManifest(
            attempt=attempt.summary(None, stored=True),
            method=attempt.method,
            target=attempt.target,
            request_headers=attempt.request_headers,
            response_headers=attempt.response_headers,
            request=request,
            response=response,
        )
        await self._filesystem.write(
            f"{prefix}/manifest.json", manifest.model_dump_json()
        )

    async def _write_body(
        self, prefix: str, side: str, body: _Body, complete: bool
    ) -> _BodyManifest:
        for index, chunk in enumerate(body.chunks):
            await self._filesystem.write(f"{prefix}/{side}-{index}", bytes(chunk))
        return _BodyManifest(
            chunks=len(body.chunks),
            size=body.size,
            complete=complete and body.size == body.observed,
        )

    async def read(self, session_id: str, ref: str) -> TraceHttpEvidence:
        prefix = f"{_session_path(session_id)}/{ref}"
        manifest = _HttpManifest.model_validate_json(
            await self._filesystem.read(f"{prefix}/manifest.json")
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
            chunk = await self._filesystem.read(f"{prefix}/{side}-{index}")
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
        await self._filesystem.delete(f"{path}/{ref}" if ref is not None else path)

    async def write_sse(
        self, session_id: str, lane: RecordedSseLane, *, create_prefix: bool
    ) -> None:
        if not lane.raw:
            return
        prefix = f"{_session_path(session_id)}/{lane.ref}"
        if create_prefix:
            await self._filesystem.mkdir(prefix)
        for index, start in enumerate(range(0, len(lane.raw), TRACE_HTTP_CHUNK_BYTES)):
            data = bytes(memoryview(lane.raw)[start : start + TRACE_HTTP_CHUNK_BYTES])
            await self._filesystem.write(f"{prefix}/sse-{index}", data)

    async def read_sse(
        self, session_id: str, ref: str, offset: int, size: int
    ) -> TraceSseFrame:
        prefix = f"{_session_path(session_id)}/{ref}"
        start, end = offset, offset + size
        data = bytearray()
        for index in range(
            start // TRACE_HTTP_CHUNK_BYTES, (end - 1) // TRACE_HTTP_CHUNK_BYTES + 1
        ):
            chunk = await self._filesystem.read(f"{prefix}/sse-{index}")
            base = index * TRACE_HTTP_CHUNK_BYTES
            data.extend(chunk[max(0, start - base) : end - base])
        if len(data) != size:
            raise ValueError("Incomplete SSE frame")
        return TraceSseFrame(data=b64encode(data).decode("ascii"))
