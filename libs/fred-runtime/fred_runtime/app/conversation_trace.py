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
from collections.abc import AsyncGenerator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, TypeVar
from urllib.parse import quote
from uuid import uuid4

import anyio
import httpx
from fastapi import HTTPException
from fred_core.history.history_schema import TraceFailureCategory
from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    TraceAdmission,
    TraceAdmissionRequest,
    TraceDegradation,
    TraceFinalization,
    TraceHistoryAccess,
    TraceHttpArtifactAccess,
    TraceHttpAttempt,
    TraceHttpEvidence,
    TraceModelArtifactAccess,
    TraceModelEvidence,
    TraceNormalization,
    TraceOutcome,
    TraceOwnerVisibilityRequest,
    TraceSseArtifactAccess,
    TraceSseEnding,
    TraceSseFrame,
    TraceSseSegment,
    TraceStorageCleanup,
    TraceStorageCleanupResult,
    TraceStoragePublication,
    TraceStorageReservation,
    TraceStorageReservationState,
    TraceToolArtifactAccess,
    TraceToolEvidence,
)
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.model.http_capture import active_http_capture
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)
from fred_pod.security.oidc_endpoints import resolve_endpoints
from fred_sdk.contracts.runtime import RuntimeEventKind, SpanPort
from pydantic import BaseModel, TypeAdapter, ValidationError

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.conversation_trace_artifacts import (
    ArtifactFiles,
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
    artifact_size,
    safe_identifier,
)
from fred_runtime.app.conversation_trace_model import ModelSnapshotCallback
from fred_runtime.runtime_support.llm_diagnostics import classify_error
from fred_runtime.runtime_support.tool_capture import active_tool_buffer

logger = logging.getLogger(__name__)
_SESSION_IDS = TypeAdapter(list[str])
_CALL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_Access = TypeVar("_Access", bound=BaseModel)
_ACTIVE_CAPTURE: ContextVar[ManagedTurnCapture | None] = ContextVar(
    "conversation_trace_capture", default=None
)


@dataclass(slots=True)
class _PreparedPublication:
    files: dict[str, ArtifactFiles]
    model_evidence: dict[str, TraceModelEvidence]
    sizes: dict[str, int]


def _prepare_publication(
    store: TraceHttpArtifactStore, buffer: HttpTurnBuffer
) -> _PreparedPublication:
    """Serialize bounded evidence away from managed stream delivery."""
    files: dict[str, ArtifactFiles] = {}
    worst_case_links: dict[str, list[TraceNormalization]] = {}
    for attempt in buffer.attempts:
        files[attempt.ref] = store.http_files(attempt)
        if attempt.sse is not None:
            files[attempt.ref].update(store.sse_files(attempt.sse))
        if attempt.tool_ref is None:
            worst_case_links.setdefault(attempt.call_id, []).append(
                attempt.normalization(raw_stored=False)
            )
    if buffer.outgoing is not None and buffer.outgoing.raw:
        files[buffer.outgoing.ref] = store.sse_files(buffer.outgoing)
    for tool in buffer.tool_calls:
        files[tool.ref] = {"tool-v1.json": tool.evidence.model_dump_json().encode()}
    model_evidence: dict[str, TraceModelEvidence] = {}
    for call in buffer.model_calls:
        # An unavailable index uses null, at least as long as any valid ordinal.
        model = call.evidence(worst_case_links.get(call.call_id, []))
        model_evidence[call.ref] = model
        files[call.ref] = {"model-v1.json": model.model_dump_json().encode()}
    return _PreparedPublication(
        files,
        model_evidence,
        {ref: artifact_size(parts) for ref, parts in files.items()},
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


def note_stream_failure(exc: Exception) -> None:
    capture = _ACTIVE_CAPTURE.get()
    if capture is not None and capture.http is not None:
        capture.watchdog_timeout = (
            classify_error(exc).get("error_code") == "stream_idle_timeout"
        )


def attach_capture_reference(span: SpanPort, *, root: bool = False) -> None:
    capture = _ACTIVE_CAPTURE.get()
    if capture is None:
        return
    with suppress(Exception):
        span.set_attribute("fred.capture.ref", capture.capture_id)
        if root:
            capture.note_span(span)


class ConversationTraceClient:
    def __init__(self, client: httpx.AsyncClient, config: AgentPodConfig) -> None:
        self._client = client
        runtime_id = quote(config.app.runtime_id, safe="")
        self._runtime_id = config.app.runtime_id
        self._control_plane_url = str(config.platform.control_plane_url).rstrip("/")
        self._url = f"{self._control_plane_url}/internal/runtimes/{runtime_id}/conversation-traces"
        self._auth: M2MBearerAuth | None = None
        self.artifacts: TraceHttpArtifactStore | None = None
        self._http_turns = 0
        self._http_workers = asyncio.Semaphore(2)
        self._serialization_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="fred-trace"
        )
        self._http_readers = asyncio.Semaphore(8)
        self._http_tasks: set[asyncio.Task[None]] = set()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._release = safe_identifier(os.environ.get("FRED_TRACE_RELEASE"))
        m2m = config.security.m2m
        if m2m.enabled:
            realm = str(m2m.realm_url).rstrip("/")
            endpoint = resolve_endpoints(
                provider=m2m.provider,
                realm_url=realm,
                token_url=str(m2m.token_url) if m2m.token_url else None,
            ).token_endpoint
            self._auth = M2MBearerAuth(
                M2MTokenProvider(
                    M2MAuthConfig(
                        keycloak_realm_url=realm,
                        client_id=m2m.client_id,
                        scope=m2m.scope,
                        token_url_override=endpoint,
                        secret_env=m2m.secret_env_var,
                    )
                )
            )

    def configure_artifacts(self, filesystem: BaseFilesystem) -> None:
        self.artifacts = TraceHttpArtifactStore(filesystem)

    async def owner_hidden_sessions(
        self, user_id: str, session_ids: list[str]
    ) -> list[str]:
        body = TraceOwnerVisibilityRequest(user_id=user_id, session_ids=session_ids)
        try:
            with anyio.fail_after(2):
                response = await self._client.post(
                    f"{self._url}/owner-hidden",
                    json=body.model_dump(mode="json"),
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                return _SESSION_IDS.validate_json(response.content)
        except (httpx.HTTPError, TimeoutError, ValidationError) as exc:
            raise HTTPException(503, "conversation_visibility_unavailable") from exc

    async def read_artifact(self, session_id: str, ref: str) -> TraceHttpEvidence:
        assert self.artifacts is not None
        async with self._http_readers:
            return await self.artifacts.read(session_id, ref)

    async def read_sse(
        self, session_id: str, ref: str, access: TraceSseArtifactAccess
    ) -> TraceSseFrame:
        assert self.artifacts is not None
        async with self._http_readers:
            return await self.artifacts.read_sse(
                session_id, ref, access.offset, access.size
            )

    async def read_model(self, session_id: str, ref: str) -> TraceModelEvidence:
        assert self.artifacts is not None
        async with self._http_readers:
            return await self.artifacts.read_model(session_id, ref)

    async def read_tool(self, session_id: str, ref: str) -> TraceToolEvidence:
        assert self.artifacts is not None
        async with self._http_readers:
            return await self.artifacts.read_tool(session_id, ref)

    def _new_http_buffer(self) -> HttpTurnBuffer | None:
        # Pod-local memory bound only. The catalog and artifacts are shared.
        if self.artifacts is None or self._http_turns >= 32:
            return None
        self._http_turns += 1
        return HttpTurnBuffer()

    def submit_http(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        task = asyncio.create_task(
            self._publish_http(
                session_id, capture_id, result, buffer, observed_through_rank
            )
        )
        self._http_tasks.add(task)
        task.add_done_callback(self._http_tasks.discard)

    def start_cleanup(self) -> None:
        """Run the runtime bucket's leased maintenance outside managed requests."""
        self._cleanup_task = asyncio.create_task(self._clean_storage())

    async def drain(self) -> None:
        """Stop maintenance and drain bounded diagnostic publishers on shutdown."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._cleanup_task
        if self._http_tasks:
            await asyncio.gather(*tuple(self._http_tasks), return_exceptions=True)
        self._serialization_pool.shutdown(wait=False, cancel_futures=True)

    async def _reserve(
        self, capture_id: str, reservation: TraceStorageReservation
    ) -> TraceStorageReservationState | None:
        """Obtain a shared reservation before issuing any artifact PUT."""
        try:
            with anyio.fail_after(0.75):
                response = await self._client.post(
                    f"{self._url}/{capture_id}/reserve",
                    json=reservation.model_dump(mode="json"),
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                return TraceStorageReservationState(response.json())
        except Exception:
            return None

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
            async with self._http_workers:
                await self._publish_reserved(
                    session_id, capture_id, result, buffer, observed_through_rank
                )
        finally:
            self._http_turns -= 1

    async def _publish_reserved(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        """Prepare exact chunks, settle successful bytes, and retain debt for failed writes."""
        attempts = buffer.close()
        store = self.artifacts
        if store is None:
            result.http_incomplete = True
            result.degradation = TraceDegradation.STORAGE
            await self.finalize(capture_id, result)
            return
        loop = asyncio.get_running_loop()
        plan = await loop.run_in_executor(
            self._serialization_pool, _prepare_publication, store, buffer
        )
        by_ref, sizes = plan.files, plan.sizes

        reservation = TraceStorageReservation(publication_id=uuid4(), objects=sizes)
        state = await self._reserve(capture_id, reservation) if sizes else None
        if state == TraceStorageReservationState.FENCED:
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
        deadline = monotonic() + 8

        async def write(ref: str, files: ArtifactFiles) -> bool:
            if publication is None:
                return False
            size = artifact_size(files)
            if size > sizes[ref] or deadline <= monotonic():
                result.degradation = TraceDegradation.STORAGE
                return False
            try:
                await store.publish(session_id, ref, files, deadline=deadline)
            except Exception:
                publication.uncertain.append(ref)
                result.degradation = TraceDegradation.STORAGE
                return False
            publication.stored[ref] = size
            return True

        lanes = []
        tool_http: dict[str, list[TraceHttpAttempt]] = {}
        normalization: dict[str, list[TraceNormalization]] = {}
        for attempt in attempts:
            stored = await write(attempt.ref, by_ref[attempt.ref])
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
                lane_stored = not attempt.sse.raw or stored
                lanes.append(attempt.sse.summary(stored=lane_stored))
            normalization.setdefault(attempt.call_id, []).append(
                attempt.normalization(raw_stored=lane_stored)
            )
        if buffer.outgoing is not None:
            lane = buffer.outgoing
            stored = not lane.raw or await write(lane.ref, by_ref[lane.ref])
            result.sse = TraceSseSegment(
                observed_through_rank=observed_through_rank,
                outgoing=lane.summary(stored=stored),
                provider=lanes,
            )
        for call in buffer.model_calls:
            evidence = plan.model_evidence[call.ref]
            actual_links = normalization.get(call.call_id, [])
            files: ArtifactFiles = by_ref[call.ref]
            if actual_links != evidence.normalization:
                evidence.normalization = actual_links
                serialized = await loop.run_in_executor(
                    self._serialization_pool, evidence.model_dump_json
                )
                files = {"model-v1.json": serialized.encode()}
            stored = await write(call.ref, files)
            result.model_calls.append(
                call.index(
                    evidence,
                    stored=stored,
                    session_id=session_id,
                    observed_through_rank=observed_through_rank,
                )
            )
        later_attempts: dict[str, float] = {}
        for tool in reversed(buffer.tool_calls):
            call_id = tool.call_id
            before = (
                later_attempts.get(call_id, float("inf"))
                if call_id is not None
                else float("inf")
            )
            if call_id is not None:
                later_attempts[call_id] = tool.started
            stored = await write(tool.ref, by_ref[tool.ref])
            result.tool_calls.append(
                tool.summary(
                    stored=stored,
                    observed_through_rank=observed_through_rank,
                    model_calls=tool.model_links(buffer.model_calls, before=before),
                    http_attempts=tool_http.get(tool.ref, []),
                )
            )
        result.tool_calls.reverse()
        # Lost acknowledgements are harmless. The control-plane transaction
        # either settled this publication or leaves it charged for later cleanup.
        await self.finalize(capture_id, result)

    async def http_access(
        self, session_id: str, exchange_id: str, ref: str, authorization: str
    ) -> TraceHttpArtifactAccess:
        return await self._artifact_access(
            "http", session_id, exchange_id, ref, authorization, TraceHttpArtifactAccess
        )

    async def sse_access(
        self,
        session_id: str,
        exchange_id: str,
        ref: str,
        index: int | None,
        authorization: str,
    ) -> TraceSseArtifactAccess:
        return await self._artifact_access(
            "sse",
            session_id,
            exchange_id,
            ref,
            authorization,
            TraceSseArtifactAccess,
            index=index,
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
        ref: str,
        authorization: str,
        decoder: type[_Access],
        *,
        index: int | None = None,
    ) -> _Access:
        key = quote(session_id, safe="")
        params: dict[str, str | int] = {
            "runtime_id": self._runtime_id,
            "exchange_id": exchange_id,
            "ref": ref,
        }
        if index is not None:
            params["index"] = index
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
    ) -> ManagedTurnCapture | None:
        try:
            request = TraceAdmissionRequest(
                session_id=session_id,
                user_id=user_id,
                exchange_id=exchange_id,
                agent_instance_id=agent_instance_id,
                history_rank=history_rank,
            )
            with anyio.fail_after(0.35):
                response = await self._client.post(
                    f"{self._url}/admit",
                    json=request.model_dump(mode="json"),
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                raw = response.json()
                if raw is not None:
                    admission = TraceAdmission.model_validate(raw)
                    return ManagedTurnCapture(
                        admission.capture_id,
                        self,
                        http=self._new_http_buffer(),
                        stream_offset_ms=admission.stream_offset_ms,
                    )
        except Exception:
            logger.debug("event=conversation_trace.admission_unavailable")
        return None

    async def finalize(self, capture_id: str, result: TraceFinalization) -> bool | None:
        """Send one index commit without encoding a second copy on the event loop."""
        try:
            if result.sse is not None or result.model_calls or result.tool_calls:
                payload = await asyncio.get_running_loop().run_in_executor(
                    self._serialization_pool, result.model_dump_json
                )
            else:
                payload = result.model_dump_json()
            with anyio.fail_after(0.75):
                response = await self._client.put(
                    f"{self._url}/{quote(capture_id, safe='')}",
                    content=payload,
                    headers={"Content-Type": "application/json"},
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                if response.status_code == 409:
                    return False
                response.raise_for_status()
                return True
        except Exception:
            logger.debug("event=conversation_trace.finalization_unavailable")
            return None


@dataclass(slots=True)
class ManagedTurnCapture:
    capture_id: str
    client: ConversationTraceClient
    outcome: TraceOutcome = TraceOutcome.UNKNOWN
    discarded: bool = False
    http: HttpTurnBuffer | None = None
    stream_offset_ms: int = 0
    watchdog_timeout: bool = False
    failure_category: TraceFailureCategory | None = None
    support_error_ref: str | None = None
    call_ids: dict[str, None] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None

    def note_call(self, call_id: str) -> None:
        if len(self.call_ids) < MAX_TRACE_CALL_IDS and _CALL_IDENTIFIER.fullmatch(
            call_id
        ):
            self.call_ids[call_id] = None

    def note_span(self, span: SpanPort) -> None:
        trace_id, span_id = span.trace_id, span.span_id
        if self.trace_id is None and trace_id and _TRACE_ID.fullmatch(trace_id):
            self.trace_id = trace_id
        if self.span_id is None and span_id and _SPAN_ID.fullmatch(span_id):
            self.span_id = span_id

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
            try:
                payload = await anext(payloads)
            except StopAsyncIteration:
                return
            finally:
                active_tool_buffer.reset(tool_token)
                _ACTIVE_CAPTURE.reset(token)
            yield payload

    async def finish(
        self,
        history_store: object,
        *,
        session_id: str,
        user_id: str,
        exchange_id: str,
        history_rank: int,
        started: float,
    ) -> None:
        duration_ms = min(int((monotonic() - started) * 1000), 2**31 - 1)
        turn_number = None
        observed_through_rank = None
        has_stream = self.http is not None and self.http.outgoing is not None
        if self.http is not None and self.http.outgoing is not None:
            ending = self.http.outgoing.ending
            if ending == TraceSseEnding.FAILED and self.watchdog_timeout:
                ending = TraceSseEnding.WATCHDOG_TIMEOUT
            self.http.outgoing.finish(monotonic(), ending)
        attempts = self.http.close() if self.http is not None else []
        if isinstance(history_store, PostgresHistoryStore) and not self.discarded:
            with suppress(Exception):
                with anyio.fail_after(0.35):
                    if attempts or has_stream:
                        boundary = await history_store.trace_boundary(
                            session_id, user_id, exchange_id
                        )
                        if boundary is not None:
                            turn_number = boundary.turn_number
                            observed_through_rank = boundary.last_rank
                    else:
                        turn_number = await history_store.exchange_number(
                            session_id, user_id, exchange_id, history_rank
                        )
        result = TraceFinalization(
            outcome=self.outcome,
            failure_category=self.failure_category,
            support_error_ref=self.support_error_ref,
            duration_ms=duration_ms,
            turn_number=turn_number,
            call_ids=list(self.call_ids),
            trace_id=self.trace_id,
            span_id=self.span_id,
            discarded=self.discarded,
            http_incomplete=self.http is None,
            degradation=(
                TraceDegradation.STORAGE
                if self.client.artifacts is None
                else TraceDegradation.QUEUE
                if self.http is None
                else None
            ),
        )
        if self.http is not None:
            if (attempts or has_stream) and not self.discarded:
                self.client.submit_http(
                    session_id,
                    self.capture_id,
                    result,
                    self.http,
                    observed_through_rank,
                )
                return
            self.client._http_turns -= 1
        await self.client.finalize(self.capture_id, result)
