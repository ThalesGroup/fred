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
import os
import re
from base64 import b64decode, b64encode
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from contextvars import Context, ContextVar
from dataclasses import dataclass, field
from functools import partial
from itertools import batched
from time import monotonic
from typing import Any, Literal, TypeVar
from urllib.parse import quote
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import HTTPException
from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    MAX_TRACE_SPANS,
    TRACE_ADMISSION_STATUS_HEADER,
    TRACE_RESUME_HEADER,
    TRACE_SEGMENT_HEADER,
    TRACE_SSE_PAGE_FRAMES,
    OtlpTraceAttribute,
    OtlpTraceSpan,
    OtlpTraceStringValue,
    TraceAdmission,
    TraceAdmissionReconciliation,
    TraceAdmissionRequest,
    TraceCheckpointStatus,
    TraceDegradation,
    TraceFinalization,
    TraceFinalizationFacts,
    TraceHistoryAccess,
    TraceHttpArtifactAccess,
    TraceHttpAttempt,
    TraceHttpEvidence,
    TraceMaskedAccess,
    TraceMaskedDocument,
    TraceMaskedEvidence,
    TraceMaskedKind,
    TraceModelArtifactAccess,
    TraceModelEvidence,
    TraceNormalization,
    TraceOutcome,
    TraceSseArtifactAccess,
    TraceSseEnding,
    TraceSseEvent,
    TraceSseFrame,
    TraceSseFrameIndexPage,
    TraceSseFrameMarker,
    TraceSseFramePage,
    TraceSseHeaderAccess,
    TraceSseHeaders,
    TraceSseKind,
    TraceSseSegment,
    TraceStorageCleanup,
    TraceStorageCleanupResult,
    TraceStoragePublication,
    TraceStorageReservation,
    TraceStorageReservationState,
    TraceToolArtifactAccess,
    TraceToolEvidence,
    TraceToolModelLink,
)
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.history.history_schema import TraceFailureCategory
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.model.http_capture import active_http_capture
from fred_core.security.backend_to_backend_auth import M2MBearerAuth
from fred_sdk.contracts.runtime import RuntimeEventKind, SpanPort
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import format_span_id, format_trace_id
from pydantic import BaseModel, ValidationError

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.conversation_trace_artifacts import (
    ArtifactFiles,
    DiscardedResponseDrains,
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
    artifact_size,
    safe_identifier,
)
from fred_runtime.app.conversation_trace_blocks import (
    TRACE_BLOCK_BYTES,
    TRACE_BLOCK_FILE,
    TraceBlockFailure,
    TraceBlockRef,
    TraceBlockWriter,
)
from fred_runtime.app.conversation_trace_masking import mask_http, mask_sse, unavailable
from fred_runtime.app.conversation_trace_model import (
    ModelSnapshotCallback,
    SnapshotWork,
)
from fred_runtime.app.conversation_trace_sse import SsePageData, provider_kind
from fred_runtime.app.conversation_trace_storage import TraceObjectIO, storage_deadline
from fred_runtime.runtime_support.checkpoints import (
    CheckpointWriteObservation,
    active_checkpoint_write,
)
from fred_runtime.runtime_support.llm_diagnostics import classify_error
from fred_runtime.runtime_support.tool_capture import active_tool_buffer

logger = logging.getLogger(__name__)
_CALL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_TRACE_METRIC_ACTOR = KPIActor(type="system")
_MAX_ADMISSIONS = 16
_ADMISSION_SECONDS = 0.9
_MAX_BUFFERS = 32
_MAX_FACT_TASKS = 128
_Access = TypeVar("_Access", bound=BaseModel)
_ReadResult = TypeVar("_ReadResult", bound=BaseModel)
_TurnNumber = Callable[[], Awaitable[int]]
_ACTIVE_CAPTURE: ContextVar[ManagedTurnCapture | None] = ContextVar(
    "conversation_trace_capture", default=None
)


@dataclass(slots=True)
class _PreparedPublication:
    files: dict[str, ArtifactFiles]
    model_evidence: dict[str, TraceModelEvidence]
    sizes: dict[str, int]
    tool_links: dict[str, list[TraceToolModelLink]]


def _prepare_publication(
    store: TraceHttpArtifactStore, buffer: HttpTurnBuffer
) -> _PreparedPublication:
    """Serialize bounded evidence away from managed stream delivery."""
    files: dict[str, ArtifactFiles] = {}
    worst_case_links: dict[str, list[TraceNormalization]] = {}
    for attempt in buffer.attempts:
        files[attempt.ref] = store.http_files(attempt)
        if attempt.sse is not None:
            attempt.sse.prepare_provider()
            files[attempt.ref].update(store.sse_files(attempt.sse))
        if attempt.tool_ref is None:
            worst_case_links.setdefault(attempt.call_id, []).append(
                attempt.normalization(raw_stored=False)
            )
    if buffer.outgoing is not None:
        outgoing_files = store.sse_files(buffer.outgoing)
        if outgoing_files:
            files[buffer.outgoing.ref] = outgoing_files
    tool_links: dict[str, list[TraceToolModelLink]] = {}
    later_attempts: dict[str, float] = {}
    for tool in reversed(buffer.tool_calls):
        before = float("inf")
        if tool.call_id is not None:
            before = later_attempts.get(tool.call_id, before)
            later_attempts[tool.call_id] = tool.started
        tool_links[tool.ref] = tool.model_links(buffer.model_calls, before=before)
        files[tool.ref] = store.tool_files(tool)
    model_evidence: dict[str, TraceModelEvidence] = {}
    for call in buffer.model_calls:
        model = call.evidence(worst_case_links.get(call.call_id, []))
        model_evidence[call.ref] = model
        files[call.ref] = store.model_files(call, model)
    sizes = {ref: artifact_size(parts) for ref, parts in files.items()}
    # The raw frame ordinal can use six more characters than its null placeholder.
    for ref, model in model_evidence.items():
        sizes[ref] += 6 * sum(len(attempt.rewrites) for attempt in model.normalization)
    return _PreparedPublication(
        files,
        model_evidence,
        sizes,
        tool_links,
    )


@contextmanager
def capture_model_http(
    call_id: str, model: str | None
) -> Iterator[ModelSnapshotCallback | None]:
    capture = _ACTIVE_CAPTURE.get()
    if capture is None:
        yield None
        return
    capture.note_call(call_id)
    observer = (
        ModelHttpCapture(capture.http, call_id, safe_identifier(model))
        if capture.http is not None
        else None
    )
    token = active_http_capture.set(observer)
    try:
        yield (
            ModelSnapshotCallback(observer)
            if observer is not None and observer.record_model_call()
            else None
        )
    finally:
        active_http_capture.reset(token)


def is_trace_capture_active() -> bool:
    return _ACTIVE_CAPTURE.get() is not None


def current_span_capture() -> ManagedTurnCapture | None:
    capture = _ACTIVE_CAPTURE.get()
    if capture and capture.capture_id and capture.http and not capture.http.closed:
        return capture
    return None


def note_stream_failure(exc: Exception) -> None:
    capture = _ACTIVE_CAPTURE.get()
    if capture is not None and capture.http is not None:
        capture.watchdog_timeout = (
            classify_error(exc).get("error_code") == "stream_idle_timeout"
        )


def attach_capture_reference(
    span: SpanPort, *, root: bool = False, call_id: str | None = None
) -> None:
    capture = _ACTIVE_CAPTURE.get()
    if capture is None:
        return
    with suppress(Exception):
        if capture.capture_id is not None:
            span.set_attribute("fred.capture.ref", capture.capture_id)
        if call_id := safe_identifier(call_id):
            span.set_attribute("fred.call.id", call_id)
        if root:
            if capture.session_id is not None:
                span.set_attribute("fred.session.id", capture.session_id)
            if capture.exchange_id is not None:
                span.set_attribute("fred.exchange.id", capture.exchange_id)
            capture.note_span(span)


def _finalization_status(committed: bool | None) -> str:
    if committed is None:
        return "unavailable"
    return "committed" if committed else "fenced"


async def _turn_number(lookup: _TurnNumber | None) -> int | None:
    if lookup is not None:
        with suppress(Exception):
            with anyio.fail_after(0.10):
                return await lookup()
    return None


class ConversationTraceClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AgentPodConfig,
        kpi: BaseKPIWriter,
        *,
        auth: M2MBearerAuth | None = None,
    ) -> None:
        self._client = client
        self._kpi = kpi
        runtime_id = quote(config.app.runtime_id, safe="")
        self._runtime_id = config.app.runtime_id
        self._control_plane_url = str(config.platform.control_plane_url).rstrip("/")
        self._url = f"{self._control_plane_url}/internal/runtimes/{runtime_id}/conversation-traces"
        self._auth = auth
        self.artifacts: TraceHttpArtifactStore | None = None
        self._active_admissions = 0
        self._http_turns = 0
        self._closing = False
        self._http_workers = asyncio.Semaphore(2)
        self._block_workers = asyncio.Semaphore(4)
        self._block_writers: set[TraceBlockWriter] = set()
        self._fact_workers = asyncio.Semaphore(8)
        self._serialization_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="fred-trace"
        )
        self._http_readers = asyncio.Semaphore(8)
        self._read_tasks: set[asyncio.Task[BaseModel]] = set()
        self._discarded_drains = DiscardedResponseDrains()
        self._snapshots = SnapshotWork()
        self._http_tasks: set[asyncio.Task[None]] = set()
        self._fact_tasks: set[asyncio.Task[None]] = set()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._release = safe_identifier(os.environ.get("FRED_TRACE_RELEASE"))
        m2m = config.security.m2m
        self._admission_enabled = m2m.enabled or not config.security.user.enabled

    def configure_artifacts(self, filesystem: BaseFilesystem | TraceObjectIO) -> None:
        self.artifacts = TraceHttpArtifactStore(filesystem)

    def _metric(
        self, name: Literal["admission", "queue", "publication", "facts"], status: str
    ) -> None:
        self._kpi.count(
            f"conversation_trace.{name}",
            dims={"status": status},
            actor=_TRACE_METRIC_ACTOR,
        )

    def note_ineligible(self) -> None:
        self._metric("admission", "filtered")

    def note_resume_boundary_unavailable(self) -> None:
        self._metric("admission", "resume_boundary_unavailable")

    async def binding_authorization(self) -> str | None:
        if self._auth is not None:
            with suppress(Exception), anyio.move_on_after(0.035):
                return await self._auth.authorization_header()
        return None

    async def read_artifact(
        self,
        session_id: str,
        ref: str,
        request_offset: int = 0,
        response_offset: int = 0,
    ) -> TraceHttpEvidence:
        assert self.artifacts is not None
        return await self._read_trace(
            partial(
                self.artifacts.read,
                request_offset=request_offset,
                response_offset=response_offset,
            ),
            session_id,
            ref,
        )

    async def read_masked_http(
        self, session_id: str, ref: str, *, remote_tool: bool
    ) -> TraceMaskedEvidence:
        """Authorize storage work through the same bounded reader used by full evidence."""
        assert self.artifacts is not None
        artifacts = self.artifacts

        async def read(key: str, artifact_ref: str) -> TraceMaskedEvidence:
            bodies = await artifacts.read_maskable_http_bodies(
                key, artifact_ref, remote_tool=remote_tool
            )

            def project() -> TraceMaskedEvidence:
                return TraceMaskedEvidence(
                    documents={
                        side: mask_http(
                            body, request=side == "request", remote_tool=remote_tool
                        )
                        if body is not None
                        else unavailable()
                        for side, body in bodies.items()
                    }
                )

            return await asyncio.get_running_loop().run_in_executor(
                self._serialization_pool, project
            )

        return await self._read_trace(read, session_id, ref)

    async def read_sse(
        self, session_id: str, ref: str, access: TraceSseArtifactAccess
    ) -> TraceSseFrame:
        assert self.artifacts is not None
        return await self._read_trace(
            self._read_paged_sse_frame, session_id, ref, access.index
        )

    async def read_sse_page(
        self, session_id: str, ref: str, page: int, *, outgoing_payload: bool = False
    ) -> TraceSseFramePage:
        if outgoing_payload:
            return await self._read_trace(
                self._export_outgoing_page, session_id, ref, page
            )
        data = await self._read_trace(
            self._read_classified_sse_page, session_id, ref, page
        )
        return TraceSseFramePage(
            frames=data.frames, start_index=page * TRACE_SSE_PAGE_FRAMES
        )

    async def read_sse_index_page(
        self, session_id: str, ref: str, page: int
    ) -> TraceSseFrameIndexPage:
        data = await self._read_trace(
            self._read_classified_sse_page, session_id, ref, page
        )
        return TraceSseFrameIndexPage(
            frames=[
                TraceSseFrameMarker(at_ms=frame.at_ms, kind=frame.kind)
                for frame in data.frames
            ],
            start_index=page * TRACE_SSE_PAGE_FRAMES,
        )

    async def _export_outgoing_page(
        self, session_id: str, ref: str, page: int
    ) -> TraceSseFramePage:
        assert self.artifacts is not None
        data = await self._read_sse_page_data(session_id, ref, page)
        ranges = []
        frames = []
        offset = 0
        for index, frame in enumerate(data.frames):
            locations = data.outgoing.get(index)
            if not locations or offset + frame.size > TRACE_BLOCK_BYTES:
                frames.append(frame.model_copy(update={"offset": None}))
                continue
            frames.append(frame.model_copy(update={"offset": offset}))
            ranges.extend(locations)
            offset += frame.size
        raw = await self.artifacts.read_block_ranges(session_id, ranges)
        return TraceSseFramePage(
            frames=frames,
            start_index=page * TRACE_SSE_PAGE_FRAMES,
            raw_data=b64encode(raw).decode("ascii") if raw else None,
        )

    async def _read_sse_page_data(
        self, session_id: str, ref: str, page: int
    ) -> SsePageData:
        assert self.artifacts is not None
        manifest = await self.artifacts.read_sse_page_manifest(session_id, ref)
        if not 0 <= page < len(manifest.pages):
            raise ValueError("Invalid SSE frame page")
        ranges = manifest.pages[page]
        if not ranges:
            return SsePageData(frames=[], outgoing={})
        raw = await self.artifacts.read_block_ranges(session_id, ranges)
        data = SsePageData.model_validate_json(raw)
        missing = set(manifest.missing_blocks)
        for index in [
            index
            for index, parts in data.outgoing.items()
            if any(part.block_id in missing for part in parts)
        ]:
            data.frames[index].offset = None
            del data.outgoing[index]
        return data

    async def _read_classified_sse_page(
        self, session_id: str, ref: str, page: int
    ) -> SsePageData:
        assert self.artifacts is not None
        data = await self._read_sse_page_data(session_id, ref, page)
        if not data.provider or not data.frames:
            return data
        start = data.frames[0].offset
        last_offset = data.frames[-1].offset
        if start is None or last_offset is None:
            return data
        end = last_offset + data.frames[-1].size
        raw = None
        if 0 < end - start <= TRACE_BLOCK_BYTES:
            with suppress(FileNotFoundError, ValueError):
                raw = await self.artifacts.read_body_range(
                    session_id, ref, start, end - start
                )
        if raw is None:
            coverage = await self.artifacts.response_coverage(
                session_id, ref, start, end
            )
            for frame in data.frames:
                offset = frame.offset
                if offset is not None and not any(
                    left <= offset and offset + frame.size <= right
                    for left, right in coverage
                ):
                    frame.offset = None
            return data

        def classify(payload: bytes) -> SsePageData:
            for frame in data.frames:
                if frame.kind == TraceSseKind.OTHER and frame.offset is not None:
                    offset = frame.offset - start
                    frame.kind = provider_kind(
                        bytearray(payload[offset : offset + frame.size])
                    )
            return data

        return await asyncio.get_running_loop().run_in_executor(
            self._serialization_pool, classify, raw
        )

    async def _read_paged_sse_frame(
        self, session_id: str, ref: str, index: int
    ) -> TraceSseFrame:
        assert self.artifacts is not None
        page, within = divmod(index, TRACE_SSE_PAGE_FRAMES)
        data = await self._read_sse_page_data(session_id, ref, page)
        if within >= len(data.frames) or (event := data.frames[within]).offset is None:
            raise ValueError("SSE frame payload missing")
        outgoing = data.outgoing.get(within)
        raw = (
            await self.artifacts.read_block_ranges(session_id, outgoing)
            if outgoing is not None
            else await self.artifacts.read_body_range(
                session_id, ref, event.offset, event.size
            )
        )
        return TraceSseFrame(data=b64encode(raw).decode("ascii"))

    async def read_sse_headers(self, session_id: str, ref: str) -> TraceSseHeaders:
        assert self.artifacts is not None
        return await self._read_trace(self.artifacts.read_sse_headers, session_id, ref)

    async def read_masked_sse(
        self, session_id: str, ref: str, index: int, *, outgoing: bool, batch: bool
    ) -> TraceMaskedEvidence:
        """Project a selected frame or a bounded batch from the private stream."""
        if not batch:
            frame = await self._read_trace(
                self._read_paged_sse_frame, session_id, ref, index
            )
            return TraceMaskedEvidence(
                documents={
                    str(index): await asyncio.get_running_loop().run_in_executor(
                        self._serialization_pool,
                        partial(mask_sse, b64decode(frame.data), outgoing=outgoing),
                    )
                }
            )
        reader = partial(self._mask_sse_page, outgoing=outgoing)
        return await self._read_trace(reader, session_id, ref, index)

    async def _mask_sse_page(
        self, session_id: str, ref: str, page: int, *, outgoing: bool
    ) -> TraceMaskedEvidence:
        assert self.artifacts is not None
        data = await self._read_sse_page_data(session_id, ref, page)
        start_index = page * TRACE_SSE_PAGE_FRAMES
        documents = {
            str(start_index + index): unavailable() for index in range(len(data.frames))
        }
        documents["index"] = TraceMaskedDocument(
            data={
                "start_index": start_index,
                "frames": [
                    {"at_ms": frame.at_ms, "kind": frame.kind.value}
                    for frame in data.frames
                ],
            }
        )
        coverage = []
        if not outgoing:
            offsets = [frame for frame in data.frames if frame.offset is not None]
            if offsets:
                first, last = offsets[0], offsets[-1]
                assert first.offset is not None and last.offset is not None
                coverage = await self.artifacts.response_coverage(
                    session_id, ref, first.offset, last.offset + last.size
                )
        groups: list[list[tuple[int, TraceSseEvent]]] = []
        size = 0
        end = -1
        for index, frame in enumerate(data.frames):
            offset = frame.offset
            if offset is None or (outgoing and not data.outgoing.get(index)):
                continue
            if not outgoing and not any(
                left <= offset and offset + frame.size <= right
                for left, right in coverage
            ):
                continue
            if (
                not groups
                or size + frame.size > TRACE_BLOCK_BYTES
                or (not outgoing and end != offset)
            ):
                groups.append([])
                size = 0
            groups[-1].append((index, frame))
            size += frame.size
            end = offset + frame.size

        def project(
            raw: bytes, group: list[tuple[int, TraceSseEvent]], budget: int
        ) -> tuple[dict[str, TraceMaskedDocument], int]:
            masked = {}
            cursor = 0
            for index, frame in group:
                end = cursor + frame.size
                if budget <= 0 or end > len(raw):
                    break
                document = mask_sse(raw[cursor:end], outgoing=outgoing)
                cursor = end
                size = len(document.model_dump_json().encode())
                if size <= budget:
                    budget -= size
                    masked[str(start_index + index)] = document
            return masked, budget

        remaining = TRACE_BLOCK_BYTES
        for group in groups:
            if remaining <= 0:
                break
            try:
                if outgoing:
                    raw = await self.artifacts.read_block_ranges(
                        session_id,
                        [part for index, _ in group for part in data.outgoing[index]],
                    )
                else:
                    start = group[0][1].offset
                    assert start is not None
                    raw = await self.artifacts.read_body_range(
                        session_id, ref, start, sum(frame.size for _, frame in group)
                    )
            except (FileNotFoundError, ValueError):
                continue
            masked, remaining = await asyncio.get_running_loop().run_in_executor(
                self._serialization_pool, project, raw, group, remaining
            )
            documents.update(masked)
        return TraceMaskedEvidence(documents=documents)

    async def read_model(self, session_id: str, ref: str) -> TraceModelEvidence:
        assert self.artifacts is not None
        return await self._read_trace(self.artifacts.read_model, session_id, ref)

    async def read_tool(self, session_id: str, ref: str) -> TraceToolEvidence:
        assert self.artifacts is not None
        return await self._read_trace(self.artifacts.read_tool, session_id, ref)

    async def _read_trace(
        self, read: Callable[..., Awaitable[_ReadResult]], *args: str | int
    ) -> _ReadResult:
        deadline = monotonic() + 5
        await self._http_readers.acquire()
        if self._closing:
            self._http_readers.release()
            raise TimeoutError("trace storage is closing")

        async def owned_read() -> _ReadResult:
            token = storage_deadline.set(deadline)
            try:
                return await read(*args)
            finally:
                storage_deadline.reset(token)
                self._http_readers.release()

        task = asyncio.create_task(owned_read(), context=Context())
        self._read_tasks.add(task)

        def settled(done: asyncio.Task[_ReadResult]) -> None:
            self._read_tasks.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(settled)
        return await asyncio.shield(task)

    def _new_http_buffer(
        self, admission: TraceAdmission, session_id: str
    ) -> HttpTurnBuffer | None:
        # Pod-local memory bound only. The catalog and artifacts are shared.
        if self.artifacts is None:
            self._metric("queue", "no_storage")
            return None
        if self._http_turns >= _MAX_BUFFERS or self._closing:
            self._metric("queue", "buffer_full")
            return None
        if not admission.streaming_blocks or admission.segment_id is None:
            self._metric("queue", "no_storage")
            return None
        writer = TraceBlockWriter(
            partial(
                self._publish_block,
                session_id,
                admission.capture_id,
                admission.segment_id,
            ),
            executor=self._serialization_pool,
        )
        self._http_turns += 1
        self._metric("queue", "buffer_acquired")
        self._block_writers.add(writer)
        return HttpTurnBuffer(
            discarded_drains=self._discarded_drains,
            snapshots=self._snapshots,
            block_writer=writer,
        )

    def release_buffer(self, buffer: HttpTurnBuffer) -> None:
        self._block_writers.discard(buffer.block_writer)
        buffer.block_writer.abort()
        self._http_turns -= 1

    def submit_facts(
        self,
        target: str | TraceAdmissionRequest,
        result: TraceFinalization,
        lookup: _TurnNumber | None,
    ) -> None:
        if self._closing or len(self._fact_tasks) >= _MAX_FACT_TASKS:
            self._metric("queue", "facts_full")
            return
        task = asyncio.create_task(
            self._publish_facts(target, result, lookup),
            context=Context(),
        )
        self._fact_tasks.add(task)
        task.add_done_callback(self._fact_tasks.discard)

    async def _publish_facts(
        self,
        target: str | TraceAdmissionRequest,
        result: TraceFinalization,
        lookup: _TurnNumber | None,
    ) -> None:
        retry_admission = None
        async with self._fact_workers:
            result.turn_number = await _turn_number(lookup)
            if isinstance(target, TraceAdmissionRequest):
                assert result.segment_id is not None
                facts = TraceFinalizationFacts.model_validate(
                    result.model_dump(include=set(TraceFinalizationFacts.model_fields))
                )
                payload = TraceAdmissionReconciliation(
                    admission=target, facts=facts
                ).model_dump_json()
                url = f"{self._url}/reconcile/{result.segment_id}"
                committed = await self._commit_index(url, payload, timeout=1)
                if committed is None and not result.discarded:
                    committed = await self._commit_index(url, payload, timeout=1)
                if committed is False or (result.discarded and committed is None):
                    retry_admission = (url, payload)
            else:
                committed = await self.finalize(target, result)
                if committed is None:
                    committed = await self.finalize(target, result)
        if retry_admission is not None:
            # A missing receipt may still be committing on the admission replica.
            await asyncio.sleep(_ADMISSION_SECONDS)
            async with self._fact_workers:
                committed = await self._commit_index(*retry_admission, timeout=1)
        self._metric("facts", _finalization_status(committed))

    def submit_http(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        if self._closing:
            self.release_buffer(buffer)
            self._metric("queue", "publisher_closed")
            return
        task = asyncio.create_task(
            self._publish_http(
                session_id,
                capture_id,
                result,
                buffer,
                observed_through_rank,
            ),
            context=Context(),
        )
        self._http_tasks.add(task)
        task.add_done_callback(self._http_tasks.discard)

    def start_cleanup(self) -> None:
        """Run the runtime bucket's leased maintenance outside managed requests."""
        self._cleanup_task = asyncio.create_task(self._clean_storage())

    async def drain(self) -> None:
        """Stop maintenance and drain bounded diagnostic publishers on shutdown."""
        self._closing = True
        pending = (
            self._http_tasks
            | self._fact_tasks
            | self._read_tasks
            | self._discarded_drains.active
        )
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            pending.add(self._cleanup_task)
        if pending:
            _, pending = await asyncio.wait(pending, timeout=10)
            for task in pending:
                task.cancel()
        for writer in self._block_writers:
            writer.abort()
        if self.artifacts is not None:
            await self.artifacts.close()
        self._snapshots.close()
        self._serialization_pool.shutdown(wait=False, cancel_futures=True)
        await self._client.aclose()

    async def _reserve(
        self, capture_id: str, reservation: TraceStorageReservation
    ) -> TraceStorageReservationState | None:
        """Obtain a shared reservation before issuing any artifact PUT."""
        try:
            with anyio.fail_after(0.75):
                response = await self._client.post(
                    f"{self._url}/{capture_id}/reserve",
                    json=reservation.model_dump(
                        mode="json", exclude_none=True, exclude_defaults=True
                    ),
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                return TraceStorageReservationState(response.json())
        except Exception:
            return None

    async def _publish_block(
        self,
        session_id: str,
        capture_id: str,
        segment_id: UUID,
        ref: TraceBlockRef,
        encoded: bytes,
    ) -> None:
        store = self.artifacts
        if store is None:
            raise RuntimeError("Trace block storage is unavailable")
        publication_id = UUID(hex=ref.id)
        reservation = TraceStorageReservation(
            publication_id=publication_id,
            segment_id=segment_id,
            objects={ref.id: len(encoded)},
            incremental=True,
        )
        async with self._block_workers:
            state = await self._reserve(capture_id, reservation)
            if state != TraceStorageReservationState.RESERVED:
                self._metric("publication", state.value if state else "unavailable")
                raise TraceBlockFailure(
                    TraceDegradation.CAPACITY
                    if state == TraceStorageReservationState.CAPACITY
                    else TraceDegradation.STORAGE
                )
            publication = TraceStoragePublication(
                publication_id=publication_id, stored={}, uncertain=[]
            )
            try:
                await store.publish(
                    session_id,
                    ref.id,
                    {TRACE_BLOCK_FILE: encoded},
                    deadline=monotonic() + 5,
                )
            except Exception:
                publication.uncertain.append(ref.id)
            else:
                publication.stored[ref.id] = len(encoded)
            url = f"{self._url}/{capture_id}/publications/{publication_id}"
            payload = publication.model_dump_json()
            settled = await self._commit_index(url, payload, timeout=1)
            if settled is None:
                settled = await self._commit_index(url, payload, timeout=1)
            if not settled or publication.uncertain:
                raise RuntimeError("Trace block publication could not be committed")

    async def _clean_storage(self) -> None:
        """Retry durable cleanup units with a bounded per-pod worker."""
        store = self.artifacts
        if store is None:
            return
        while True:
            more = False
            try:
                with anyio.fail_after(2):
                    response = await self._client.post(
                        f"{self._url}/cleanup",
                        auth=self._auth
                        if self._auth is not None
                        else httpx.USE_CLIENT_DEFAULT,
                    )
                    response.raise_for_status()
                raw = response.json()
                if raw is not None:
                    work = TraceStorageCleanup.model_validate(raw)
                    more = await self._clean_storage_unit(store, work)
            except Exception:
                logger.debug("event=conversation_trace.storage_cleanup_unavailable")
            await asyncio.sleep(0.25 if more else 5)

    async def _clean_storage_unit(
        self,
        store: TraceHttpArtifactStore,
        work: TraceStorageCleanup,
    ) -> bool:
        """Measure or erase an immutable opaque prefix under the current lease."""
        result = TraceStorageCleanupResult(lease=work.lease)
        token = storage_deadline.set(monotonic() + 30)
        try:
            with anyio.fail_after(30):
                if work.measure:
                    result.measured = {
                        ref: await store.measure(work.session_id, ref)
                        for ref in work.refs
                    }
                else:
                    for ref in work.refs:
                        await store.erase(work.session_id, ref)
        except Exception:
            result.success = False
        finally:
            storage_deadline.reset(token)
        with anyio.fail_after(2):
            response = await self._client.put(
                f"{self._url}/cleanup/{work.id}",
                json=result.model_dump(mode="json"),
                auth=self._auth if self._auth is not None else httpx.USE_CLIENT_DEFAULT,
            )
            response.raise_for_status()
        return result.success

    async def _publish_http(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        """Publish admitted evidence under one globally reserved write budget."""
        try:
            await buffer.settle_discarded_bodies()
            drain = await buffer.block_writer.finish()
            buffer.mark_failed_blocks(drain.failed_blocks)
            if buffer.outgoing is not None:
                buffer.outgoing.mark_failed_blocks(drain.failed_blocks)
            for attempt in buffer.attempts:
                if attempt.sse is not None:
                    attempt.sse.mark_failed_blocks(drain.failed_blocks)
            if drain.dropped_bytes or drain.failed_blocks:
                buffer.incomplete = True
                result.degradation = drain.degradation or TraceDegradation.QUEUE
            async with self._http_workers:
                await self._publish_reserved(
                    session_id, capture_id, result, buffer, observed_through_rank
                )
        except Exception:
            self._metric("publication", "error")
            result.recording_complete = False
            await self._publish_missing_evidence(capture_id, result)
        finally:
            self.release_buffer(buffer)

    async def _publish_missing_evidence(
        self, capture_id: str, result: TraceFinalization
    ) -> None:
        fallback = result.model_copy(
            update={
                "http_attempts": [],
                "sse": None,
                "model_calls": [],
                "tool_calls": [],
                "http_incomplete": True,
                "recording_complete": False
                if result.recording_complete is not None
                else None,
                "degradation": result.degradation or TraceDegradation.STORAGE,
                "storage": None,
            }
        )
        committed = await self.finalize(capture_id, fallback)
        self._metric("facts", _finalization_status(committed))

    async def _publish_reserved(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        """Prepare exact chunks, settle successful bytes, and retain debt for failed writes."""
        attempts = buffer.attempts
        store = self.artifacts
        if store is None:
            result.http_incomplete = True
            result.degradation = TraceDegradation.STORAGE
            result.recording_complete = False
            await self.finalize(capture_id, result)
            return
        loop = asyncio.get_running_loop()
        plan = await loop.run_in_executor(
            self._serialization_pool, _prepare_publication, store, buffer
        )
        by_ref, sizes = plan.files, plan.sizes

        assert result.segment_id is not None
        reservation = TraceStorageReservation(
            publication_id=result.segment_id,
            objects=sizes,
            segment_id=result.segment_id,
        )
        state = await self._reserve(capture_id, reservation) if sizes else None
        if state == TraceStorageReservationState.FENCED:
            self._metric("publication", "fenced")
            return
        publication = (
            TraceStoragePublication(
                publication_id=reservation.publication_id,
                stored={},
                uncertain=[],
            )
            if state == TraceStorageReservationState.RESERVED
            else None
        )
        result.storage = publication
        storage_unavailable = bool(sizes) and publication is None
        result.http_incomplete = buffer.incomplete or storage_unavailable
        if storage_unavailable:
            result.degradation = (
                TraceDegradation.CAPACITY
                if state == TraceStorageReservationState.CAPACITY
                else TraceDegradation.STORAGE
            )
            self._metric(
                "publication", state.value if state is not None else "unavailable"
            )

        async def write(ref: str, files: ArtifactFiles) -> bool:
            if publication is None:
                return False
            size = artifact_size(files)
            if size > sizes[ref]:
                result.degradation = TraceDegradation.STORAGE
                result.http_incomplete = True
                return False
            try:
                async with self._block_workers:
                    await store.publish(
                        session_id, ref, files, deadline=monotonic() + 5
                    )
            except Exception:
                publication.uncertain.append(ref)
                result.degradation = TraceDegradation.STORAGE
                result.http_incomplete = True
                return False
            publication.stored[ref] = size
            return True

        async def publish_files(refs: Iterator[str]) -> dict[str, bool]:
            published = {}
            for group in batched(refs, 4):
                statuses = await asyncio.gather(
                    *(write(ref, by_ref[ref]) for ref in group)
                )
                published.update(zip(group, statuses, strict=True))
            return published

        attempt_refs = [attempt.ref for attempt in attempts]
        # Make the end of a failed turn durable even if background storage slows.
        attempt_refs.reverse()
        stored_attempts = await publish_files(iter(attempt_refs))
        lanes = []
        tool_http: dict[str, list[TraceHttpAttempt]] = {}
        normalization: dict[str, list[TraceNormalization]] = {}
        for attempt in attempts:
            stored = stored_attempts[attempt.ref]
            summary = attempt.summary(
                self._release,
                stored=stored,
                observed_through_rank=observed_through_rank,
            )
            result.http_attempts.append(summary)
            if attempt.tool_ref is not None:
                tool_http.setdefault(attempt.tool_ref, []).append(summary)
                continue
            lane_stored = False
            if attempt.sse is not None:
                lane_stored = stored
                lanes.append(attempt.sse.summary(stored=lane_stored))
            normalization.setdefault(attempt.call_id, []).append(
                attempt.normalization(raw_stored=lane_stored)
            )
        outgoing = None
        lane = buffer.outgoing
        if lane is not None:
            stored = lane.ref in by_ref and await write(lane.ref, by_ref[lane.ref])
            outgoing = lane.summary(stored=stored)
        if outgoing is not None or lanes:
            result.sse = TraceSseSegment(
                observed_through_rank=observed_through_rank,
                outgoing=outgoing,
                provider=lanes,
            )
        for call in buffer.model_calls:
            evidence = plan.model_evidence[call.ref]
            actual_links = normalization.get(call.call_id, [])
            if actual_links != evidence.normalization:
                evidence.normalization = actual_links
                by_ref[call.ref] = await loop.run_in_executor(
                    self._serialization_pool, store.model_files, call, evidence
                )
        stored_models = await publish_files(call.ref for call in buffer.model_calls)
        for call in buffer.model_calls:
            result.model_calls.append(
                call.index(
                    plan.model_evidence[call.ref],
                    stored=stored_models[call.ref],
                    session_id=session_id,
                    observed_through_rank=observed_through_rank,
                )
            )
        stored_tools = await publish_files(tool.ref for tool in buffer.tool_calls)
        for tool in buffer.tool_calls:
            result.tool_calls.append(
                tool.summary(
                    stored=stored_tools[tool.ref],
                    observed_through_rank=observed_through_rank,
                    model_calls=plan.tool_links[tool.ref],
                    http_attempts=tool_http.get(tool.ref, []),
                )
            )
        # Lost acknowledgements are harmless. The control-plane transaction
        # either settled this publication or leaves it charged for later cleanup.
        result.recording_complete = not result.http_incomplete
        committed = await self.finalize(capture_id, result)
        if committed is None:
            committed = await self.finalize(capture_id, result)
        self._metric(
            "publication",
            _finalization_status(committed)
            if result.degradation is None or committed is not True
            else "degraded",
        )
        if committed is None:
            # The first commit may have succeeded. A completed receipt leaves
            # it intact. Otherwise only safe facts and partial evidence settle,
            # and the charged reservation stays subject to leased cleanup.
            await self._publish_missing_evidence(capture_id, result)

    async def http_access(
        self, session_id: str, exchange_id: str, ref: str, authorization: str
    ) -> TraceHttpArtifactAccess:
        return await self._artifact_access(
            "http", session_id, exchange_id, ref, authorization, TraceHttpArtifactAccess
        )

    async def masked_access(
        self,
        session_id: str,
        exchange_id: str,
        kind: TraceMaskedKind,
        ref: str | None,
        authorization: str,
    ) -> TraceMaskedAccess:
        return await self._artifact_access(
            "masked",
            session_id,
            exchange_id,
            ref,
            authorization,
            TraceMaskedAccess,
            evidence_kind=kind,
        )

    async def sse_access(
        self,
        session_id: str,
        exchange_id: str,
        ref: str,
        index: int,
        authorization: str,
        *,
        metadata_only: bool = False,
    ) -> TraceSseArtifactAccess:
        return await self._artifact_access(
            "sse",
            session_id,
            exchange_id,
            ref,
            authorization,
            TraceSseArtifactAccess,
            index=index,
            metadata_only=metadata_only,
        )

    async def sse_header_access(
        self, session_id: str, exchange_id: str, ref: str, authorization: str
    ) -> TraceSseHeaderAccess:
        return await self._artifact_access(
            "sse-header",
            session_id,
            exchange_id,
            ref,
            authorization,
            TraceSseHeaderAccess,
        )

    async def model_access(
        self, session_id: str, exchange_id: str, ref: str, authorization: str
    ) -> TraceModelArtifactAccess:
        return await self._artifact_access(
            "model",
            session_id,
            exchange_id,
            ref,
            authorization,
            TraceModelArtifactAccess,
        )

    async def tool_access(
        self, session_id: str, exchange_id: str, ref: str, authorization: str
    ) -> TraceToolArtifactAccess:
        return await self._artifact_access(
            "tool", session_id, exchange_id, ref, authorization, TraceToolArtifactAccess
        )

    async def _artifact_access(
        self,
        kind: str,
        session_id: str,
        exchange_id: str,
        ref: str | None,
        authorization: str,
        decoder: type[_Access],
        *,
        index: int | None = None,
        evidence_kind: TraceMaskedKind | None = None,
        metadata_only: bool = False,
    ) -> _Access:
        key = quote(session_id, safe="")
        params: dict[str, str | int] = {
            "runtime_id": self._runtime_id,
            "exchange_id": exchange_id,
        }
        if ref is not None:
            params["ref"] = ref
        if evidence_kind is not None:
            params["kind"] = evidence_kind
        if index is not None:
            params["index"] = index
        if metadata_only:
            params["metadata_only"] = "true"
        try:
            response = await self._client.get(
                f"{self._control_plane_url}/admin/conversation-traces/{key}/{kind}-access",
                headers={"Authorization": authorization},
                params=params,
            )
            if response.status_code in {401, 403, 404}:
                raise HTTPException(403, f"trace_{kind}_access_denied")
            response.raise_for_status()
            return decoder.model_validate_json(response.content)
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, f"trace_{kind}_unavailable") from exc

    async def history_access(
        self, session_id: str, authorization: str, exchange_id: str | None = None
    ) -> TraceHistoryAccess:
        key = quote(session_id, safe="")
        params = {"runtime_id": self._runtime_id}
        if exchange_id is not None:
            params["exchange_id"] = exchange_id
        try:
            response = await self._client.get(
                f"{self._control_plane_url}/admin/conversation-traces/{key}/history-access",
                headers={"Authorization": authorization},
                params=params,
            )
            if response.status_code in {401, 403, 404}:
                raise HTTPException(403, "trace_history_access_denied")
            response.raise_for_status()
            return TraceHistoryAccess.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise HTTPException(503, "trace_history_access_unavailable") from exc

    async def admit(
        self,
        *,
        session_id: str,
        user_id: str,
        exchange_id: str,
        agent_instance_id: str,
        history_rank: int,
        resuming: bool = False,
    ) -> ManagedTurnCapture | None:
        if not self._admission_enabled:
            self.note_ineligible()
            return None
        if self._closing or self._active_admissions >= _MAX_ADMISSIONS:
            self._metric("admission", "busy")
            return None
        self._active_admissions += 1
        started = monotonic()
        status = "rejected"
        request = None
        segment_id = uuid4()
        try:
            request = TraceAdmissionRequest(
                session_id=session_id,
                user_id=user_id,
                exchange_id=exchange_id,
                agent_instance_id=agent_instance_id,
                history_rank=history_rank,
            )
            headers = {TRACE_SEGMENT_HEADER: str(segment_id)}
            if resuming:
                headers[TRACE_RESUME_HEADER] = "true"
            with anyio.fail_after(_ADMISSION_SECONDS):
                response = await self._client.post(
                    f"{self._url}/admit",
                    json=request.model_dump(mode="json"),
                    headers=headers,
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                raw = response.json()
                if (
                    response.headers.get(TRACE_ADMISSION_STATUS_HEADER)
                    == "flush_in_progress"
                ):
                    status = "flush_in_progress"
                if raw is not None:
                    admission = TraceAdmission.model_validate(raw)
                    if admission.segment_id != segment_id:
                        raise ValueError("admission segment mismatch")
                    status = "admitted"
                    return ManagedTurnCapture(
                        admission.capture_id,
                        self,
                        http=self._new_http_buffer(admission, session_id),
                        stream_offset_ms=admission.stream_offset_ms,
                        segment_id=admission.segment_id,
                        history_rank=history_rank,
                        session_id=session_id,
                        exchange_id=exchange_id,
                    )
        except asyncio.CancelledError:
            status = "cancelled"
            if request is not None:
                self.submit_facts(
                    request,
                    TraceFinalization(
                        outcome=TraceOutcome.UNKNOWN,
                        duration_ms=0,
                        segment_id=segment_id,
                        discarded=True,
                    ),
                    None,
                )
            raise
        except (TimeoutError, httpx.TimeoutException):
            status = "timeout"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {400, 401, 403, 404, 422}:
                status = "unavailable"
        except Exception:
            status = "unavailable"
            logger.debug("event=conversation_trace.admission_unavailable")
        finally:
            self._active_admissions -= 1
            self._metric("admission", status)
            self._kpi.emit(
                name="conversation_trace.admission_latency_ms",
                type="timer",
                value=(monotonic() - started) * 1000,
                unit="ms",
                dims={"status": status},
                actor=_TRACE_METRIC_ACTOR,
            )
        if request is not None and status in {"unavailable", "timeout"}:
            return ManagedTurnCapture(
                None,
                self,
                segment_id=segment_id,
                history_rank=history_rank,
                uncertain_admission=request,
            )
        return None

    async def finalize(self, capture_id: str, result: TraceFinalization) -> bool | None:
        """Send one index commit without encoding a second copy on the event loop."""
        try:
            exclude = (
                {"segment_id", "evidence_pending"}
                if result.segment_id is None
                else set()
            )
            if not result.otel_spans:
                exclude.add("otel_spans")
            if result.recording_complete is None:
                exclude.add("recording_complete")
            if (
                result.sse is not None
                or result.model_calls
                or result.tool_calls
                or result.otel_spans
            ):
                payload = await asyncio.get_running_loop().run_in_executor(
                    self._serialization_pool,
                    lambda: result.model_dump_json(exclude=exclude),
                )
            else:
                payload = result.model_dump_json(exclude=exclude)
            url = f"{self._url}/{quote(capture_id, safe='')}"
            return await self._commit_index(
                url,
                payload,
                timeout=0.75,
                without_spans=(
                    lambda: result.model_dump_json(exclude=exclude | {"otel_spans"})
                )
                if result.otel_spans
                else None,
            )
        except Exception:
            logger.debug("event=conversation_trace.finalization_unavailable")
            return None

    async def _commit_index(
        self,
        url: str,
        payload: str,
        *,
        timeout: float,
        without_spans: Callable[[], str] | None = None,
    ) -> bool | None:
        try:
            with anyio.fail_after(timeout):

                async def put(body: str) -> httpx.Response:
                    return await self._client.put(
                        url,
                        content=body,
                        headers={"Content-Type": "application/json"},
                        auth=self._auth
                        if self._auth is not None
                        else httpx.USE_CLIENT_DEFAULT,
                    )

                response = await put(payload)
                if without_spans is not None and response.status_code == 422:
                    errors = response.json().get("detail", [])
                    if any(
                        error.get("type") == "extra_forbidden"
                        and error.get("loc") == ["body", "otel_spans"]
                        for error in errors
                    ):
                        # An older replica can still publish the evidence indexes.
                        legacy = await asyncio.get_running_loop().run_in_executor(
                            self._serialization_pool, without_spans
                        )
                        response = await put(legacy)
                if response.status_code == 409:
                    return False
                response.raise_for_status()
                return True
        except Exception:
            logger.debug("event=conversation_trace.finalization_unavailable")
            return None


@dataclass(slots=True)
class ManagedTurnCapture:
    capture_id: str | None
    client: ConversationTraceClient
    outcome: TraceOutcome = TraceOutcome.UNKNOWN
    discarded: bool = False
    http: HttpTurnBuffer | None = None
    stream_offset_ms: int = 0
    segment_id: UUID | None = None
    history_rank: int = 0
    watchdog_timeout: bool = False
    failure_category: TraceFailureCategory | None = None
    support_error_ref: str | None = None
    call_ids: dict[str, None] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None
    session_id: str | None = None
    exchange_id: str | None = None
    otel_spans: list[OtlpTraceSpan] = field(default_factory=list)
    checkpoint_status: TraceCheckpointStatus = TraceCheckpointStatus.UNKNOWN
    checkpoint_write: CheckpointWriteObservation | None = None
    uncertain_admission: TraceAdmissionRequest | None = None

    def note_call(self, call_id: str) -> None:
        if _CALL_IDENTIFIER.fullmatch(call_id) and (
            len(self.call_ids) < MAX_TRACE_CALL_IDS or self.http is not None
        ):
            self.call_ids[call_id] = None

    def note_span(self, span: SpanPort) -> None:
        trace_id, span_id = span.trace_id, span.span_id
        if self.trace_id is None and trace_id and _TRACE_ID.fullmatch(trace_id):
            self.trace_id = trace_id
        if self.span_id is None and span_id and _SPAN_ID.fullmatch(span_id):
            self.span_id = span_id

    def note_otel_span(self, span: ReadableSpan) -> None:
        attributes = span.attributes or {}
        if attributes.get("fred.capture.ref") != self.capture_id:
            return
        if len(self.otel_spans) >= MAX_TRACE_SPANS and self.http is None:
            return
        context, name = span.context, safe_identifier(span.name)
        if (
            not context
            or not context.is_valid
            or not name
            or span.start_time is None
            or span.end_time is None
        ):
            return
        self.otel_spans.append(
            OtlpTraceSpan(
                trace_id=format_trace_id(context.trace_id),
                span_id=format_span_id(context.span_id),
                parent_span_id=format_span_id(span.parent.span_id)
                if span.parent
                else "",
                name=name,
                start_time_unix_nano=str(span.start_time),
                end_time_unix_nano=str(span.end_time),
                attributes=[
                    OtlpTraceAttribute(
                        key=key, value=OtlpTraceStringValue(string_value=value)
                    )
                    for key in (
                        "fred.capture.ref",
                        "fred.call.id",
                        "fred.evidence.ref",
                        "fred.session.id",
                        "fred.exchange.id",
                    )
                    if isinstance(raw := attributes.get(key), str)
                    and (value := safe_identifier(raw)) is not None
                ],
            )
        )

    def note_event(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if kind == RuntimeEventKind.FINAL:
            self.outcome = TraceOutcome.COMPLETED
        elif kind == RuntimeEventKind.EXECUTION_ERROR:
            self.outcome = TraceOutcome.FAILED
            raw_ref = event.get("support_error_ref")
            if isinstance(raw_ref, str) and _TRACE_ID.fullmatch(raw_ref):
                self.support_error_ref = raw_ref
            raw_category = event.get("trace_failure_category")
            if isinstance(raw_category, str):
                with suppress(ValueError):
                    self.failure_category = TraceFailureCategory(raw_category)
        elif kind == RuntimeEventKind.AWAITING_HUMAN:
            self.outcome = TraceOutcome.PAUSED
        elif kind == RuntimeEventKind.EXECUTION_INTERRUPTED:
            self.discarded = True
        elif kind == RuntimeEventKind.TOOL_CALL:
            call_id = event.get("call_id")
            if isinstance(call_id, str):
                self.note_call(call_id)

    async def iterate(
        self, payloads: AsyncGenerator[dict[str, Any], None]
    ) -> AsyncGenerator[dict[str, Any], None]:
        while True:
            token = _ACTIVE_CAPTURE.set(self)
            tool_token = active_tool_buffer.set(self.http)
            checkpoint_token = active_checkpoint_write.set(self.checkpoint_write)
            try:
                payload = await anext(payloads)
            except StopAsyncIteration:
                return
            finally:
                active_checkpoint_write.reset(checkpoint_token)
                active_tool_buffer.reset(tool_token)
                _ACTIVE_CAPTURE.reset(token)
            yield payload

    def finish(
        self,
        history_store: object,
        *,
        session_id: str,
        user_id: str,
        exchange_id: str,
        observed_through_rank: int | None,
        started: float,
    ) -> None:
        duration_ms = min(int((monotonic() - started) * 1000), 2**31 - 1)
        has_stream = self.http is not None and self.http.outgoing is not None
        if self.http is not None and self.http.outgoing is not None:
            ending = self.http.outgoing.ending
            if ending == TraceSseEnding.FAILED and self.watchdog_timeout:
                ending = TraceSseEnding.WATCHDOG_TIMEOUT
            self.http.outgoing.finish(monotonic(), ending)
        if self.http is not None:
            self.http.close()
        has_evidence = self.http is not None and (
            has_stream
            or self.http.attempts
            or self.http.model_calls
            or self.http.tool_calls
        )
        result = TraceFinalization(
            outcome=self.outcome,
            failure_category=self.failure_category,
            support_error_ref=self.support_error_ref,
            duration_ms=duration_ms,
            call_ids=list(self.call_ids),
            trace_id=self.trace_id,
            span_id=self.span_id,
            checkpoint_status=(
                TraceCheckpointStatus.PERSISTED
                if self.checkpoint_write is not None and self.checkpoint_write.persisted
                else self.checkpoint_status
            ),
            discarded=self.discarded,
            segment_id=self.segment_id,
            http_incomplete=self.http is None,
            otel_spans=self.otel_spans,
            degradation=(
                TraceDegradation.STORAGE
                if self.client.artifacts is None
                else TraceDegradation.QUEUE
                if self.http is None
                else None
            ),
        )
        lookup = (
            partial(
                history_store.exchange_number,
                session_id,
                user_id,
                exchange_id,
                self.history_rank,
            )
            if isinstance(history_store, PostgresHistoryStore) and not self.discarded
            else None
        )
        buffer = self.http
        if self.capture_id is None:
            assert self.uncertain_admission is not None
            self.client.submit_facts(self.uncertain_admission, result, lookup)
            return
        if (
            buffer is not None
            and self.segment_id is not None
            and has_evidence
            and not self.discarded
        ):
            self.client.submit_facts(
                self.capture_id,
                result.model_copy(
                    update={"evidence_pending": True, "otel_spans": []}
                ).model_copy(deep=True),
                lookup,
            )
            self.client.submit_http(
                session_id,
                self.capture_id,
                result,
                buffer,
                observed_through_rank,
            )
            return
        if buffer is not None:
            self.client.release_buffer(buffer)
        self.client.submit_facts(self.capture_id, result, lookup)
