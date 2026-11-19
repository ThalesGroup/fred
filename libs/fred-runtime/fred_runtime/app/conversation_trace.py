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

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
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
    TraceOutcome,
)
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)
from fred_pod.security.oidc_endpoints import resolve_endpoints
from fred_sdk.contracts.runtime import RuntimeEventKind, SpanPort
from pydantic import ValidationError

from fred_runtime.app.config import AgentPodConfig

logger = logging.getLogger(__name__)
_CALL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_ACTIVE_CAPTURE: ContextVar[ManagedTurnCapture | None] = ContextVar(
    "conversation_trace_capture", default=None
)


def trace_call(call_id: str) -> None:
    capture = _ACTIVE_CAPTURE.get()
    if capture is not None:
        capture.note_call(call_id)


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
                    return ManagedTurnCapture(admission.capture_id, self)
        except Exception:
            logger.debug("event=conversation_trace.admission_unavailable")
        return None

    async def finalize(self, capture_id: str, result: TraceFinalization) -> None:
        try:
            with anyio.fail_after(0.75):
                response = await self._client.put(
                    f"{self._url}/{quote(capture_id, safe='')}",
                    json=result.model_dump(mode="json"),
                    auth=self._auth
                    if self._auth is not None
                    else httpx.USE_CLIENT_DEFAULT,
                )
                response.raise_for_status()
        except Exception:
            logger.debug("event=conversation_trace.finalization_unavailable")


@dataclass(slots=True)
class ManagedTurnCapture:
    capture_id: str
    client: ConversationTraceClient
    outcome: TraceOutcome = TraceOutcome.UNKNOWN
    discarded: bool = False
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
            try:
                payload = await anext(payloads)
            except StopAsyncIteration:
                return
            finally:
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
        if isinstance(history_store, PostgresHistoryStore) and not self.discarded:
            with suppress(Exception):
                with anyio.fail_after(0.35):
                    turn_number = await history_store.exchange_number(
                        session_id, user_id, exchange_id, history_rank
                    )
        await self.client.finalize(
            self.capture_id,
            TraceFinalization(
                outcome=self.outcome,
                duration_ms=duration_ms,
                turn_number=turn_number,
                call_ids=list(self.call_ids),
                trace_id=self.trace_id,
                span_id=self.span_id,
                discarded=self.discarded,
            ),
        )
