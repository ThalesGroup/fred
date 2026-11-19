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
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, TypeVar
from urllib.parse import quote

import anyio
import httpx
from fastapi import HTTPException
from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    TraceAdmission,
    TraceAdmissionRequest,
    TraceFinalization,
    TraceHistoryAccess,
    TraceHttpArtifactAccess,
    TraceHttpAttempt,
    TraceHttpEvidence,
    TraceModelArtifactAccess,
    TraceModelEvidence,
    TraceNormalization,
    TraceOutcome,
    TraceSseArtifactAccess,
    TraceSseEnding,
    TraceSseFrame,
    TraceSseSegment,
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
from pydantic import BaseModel, ValidationError

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.conversation_trace_artifacts import (
    HttpTurnBuffer,
    ModelHttpCapture,
    TraceHttpArtifactStore,
    safe_identifier,
)
from fred_runtime.app.conversation_trace_model import ModelSnapshotCallback
from fred_runtime.app.conversation_trace_sse import RecordedSseLane
from fred_runtime.runtime_support.llm_diagnostics import classify_error
from fred_runtime.runtime_support.tool_capture import active_tool_buffer

logger = logging.getLogger(__name__)
_CALL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_Access = TypeVar("_Access", bound=BaseModel)
_ACTIVE_CAPTURE: ContextVar[ManagedTurnCapture | None] = ContextVar(
    "conversation_trace_capture", default=None
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
        self._http_workers = asyncio.Semaphore(4)
        self._http_readers = asyncio.Semaphore(8)
        self._http_tasks: set[asyncio.Task[None]] = set()
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

    async def drain(self) -> None:
        if self._http_tasks:
            await asyncio.gather(*tuple(self._http_tasks), return_exceptions=True)

    async def _can_write(self, capture_id: str) -> bool | None:
        try:
            with anyio.fail_after(0.75):
                response = await self._client.get(
                    f"{self._url}/{capture_id}/writable",
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
                return response.json() is True
        except Exception:
            return None

    async def _erase_attempts(self, session_id: str, attempts: list[str]) -> None:
        store = self.artifacts
        if store is None:
            return
        try:
            with anyio.fail_after(4):
                for ref in attempts:
                    await store.erase(session_id, ref)
        except Exception:
            logger.warning("event=conversation_trace.http_artifact_cleanup_failed")

    async def _publish_http(
        self,
        session_id: str,
        capture_id: str,
        result: TraceFinalization,
        buffer: HttpTurnBuffer,
        observed_through_rank: int | None,
    ) -> None:
        refs: list[str] = []
        try:
            attempts = buffer.close()
            store = self.artifacts
            async with self._http_workers:
                permitted = await self._can_write(capture_id)
                if permitted is False:
                    return
                summaries: list[TraceHttpAttempt] = []
                lanes = []
                tool_http: dict[str, list[TraceHttpAttempt]] = {}
                normalization: dict[str, list[TraceNormalization]] = {}
                # Keep order and cap per-pod in-flight writes across all turns.
                deadline = monotonic() + 8
                for attempt in attempts:
                    stored = False
                    if permitted and store is not None and deadline > monotonic():
                        try:
                            with anyio.fail_after(max(0, deadline - monotonic())):
                                await store.write(session_id, attempt)
                            refs.append(attempt.ref)
                            stored = True
                        except Exception:
                            logger.warning(
                                "event=conversation_trace.http_artifact_write_failed"
                            )
                            await self._erase_attempts(session_id, [attempt.ref])
                    summaries.append(
                        attempt.summary(
                            self._release,
                            stored=stored,
                            observed_through_rank=observed_through_rank,
                        )
                    )
                    if attempt.tool_ref is not None:
                        tool_http.setdefault(attempt.tool_ref, []).append(summaries[-1])
                        continue
                    lane_stored = False
                    if attempt.sse is not None:
                        lane_stored = await self._publish_sse_lane(
                            session_id,
                            attempt.sse,
                            create_prefix=not stored,
                            permitted=bool(permitted),
                            deadline=deadline,
                        )
                        if lane_stored and attempt.sse.raw and not stored:
                            refs.append(attempt.ref)
                        lanes.append(attempt.sse.summary(stored=lane_stored))
                    normalization.setdefault(attempt.call_id, []).append(
                        attempt.normalization(raw_stored=lane_stored)
                    )
                result.http_attempts = summaries
                result.http_incomplete = buffer.incomplete
                if buffer.outgoing is not None:
                    lane = buffer.outgoing
                    stored = await self._publish_sse_lane(
                        session_id,
                        lane,
                        create_prefix=True,
                        permitted=bool(permitted),
                        deadline=deadline,
                    )
                    if stored and lane.raw:
                        refs.append(lane.ref)
                    result.sse = TraceSseSegment(
                        observed_through_rank=observed_through_rank,
                        outgoing=lane.summary(stored=stored),
                        provider=lanes,
                    )
                for call in buffer.model_calls:
                    evidence = call.evidence(normalization.get(call.call_id, []))
                    stored = False
                    if permitted and store is not None and deadline > monotonic():
                        try:
                            with anyio.fail_after(max(0, deadline - monotonic())):
                                await store.write_model(session_id, call.ref, evidence)
                            refs.append(call.ref)
                            stored = True
                        except Exception:
                            logger.warning(
                                "event=conversation_trace.model_artifact_write_failed"
                            )
                            await self._erase_attempts(session_id, [call.ref])
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
                    links = tool.model_links(buffer.model_calls, before=before)
                    stored = False
                    if permitted and store is not None and deadline > monotonic():
                        try:
                            with anyio.fail_after(max(0, deadline - monotonic())):
                                await store.write_tool(
                                    session_id, tool.ref, tool.evidence
                                )
                            refs.append(tool.ref)
                            stored = True
                        except Exception:
                            logger.warning(
                                "event=conversation_trace.tool_artifact_write_failed"
                            )
                            await self._erase_attempts(session_id, [tool.ref])
                    result.tool_calls.append(
                        tool.summary(
                            stored=stored,
                            observed_through_rank=observed_through_rank,
                            model_calls=links,
                            http_attempts=tool_http.get(tool.ref, []),
                        )
                    )
                result.tool_calls.reverse()
                published = await self.finalize(capture_id, result)
                # A definitive rejection fences erasure and duplicate finalizations.
                # A lost response can still mean the index committed.
                if published is False:
                    await self._erase_attempts(session_id, refs)
        finally:
            self._http_turns -= 1

    async def _publish_sse_lane(
        self,
        session_id: str,
        lane: RecordedSseLane,
        *,
        create_prefix: bool,
        permitted: bool,
        deadline: float,
    ) -> bool:
        if not lane.raw:
            return True
        if not permitted or self.artifacts is None or deadline <= monotonic():
            return False
        try:
            with anyio.fail_after(max(0, deadline - monotonic())):
                await self.artifacts.write_sse(
                    session_id, lane, create_prefix=create_prefix
                )
        except Exception:
            logger.warning("event=conversation_trace.sse_artifact_write_failed")
            if create_prefix:
                await self._erase_attempts(session_id, [lane.ref])
            return False
        return True

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
        index: int,
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
        try:
            with anyio.fail_after(0.75):
                response = await self._client.put(
                    f"{self._url}/{quote(capture_id, safe='')}",
                    json=result.model_dump(mode="json"),
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
            duration_ms=duration_ms,
            turn_number=turn_number,
            call_ids=list(self.call_ids),
            trace_id=self.trace_id,
            span_id=self.span_id,
            discarded=self.discarded,
            http_incomplete=self.http is None,
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
