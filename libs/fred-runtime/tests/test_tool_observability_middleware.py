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

"""
Tests for `ToolObservabilityMiddleware` (#2011).

This is the ported KPI/audit coverage that used to live in
`test_context_aware_tool.py` (see that file's own docstring), now exercised
through `awrap_tool_call` directly — the same generic chokepoint every tool
call (MCP-catalog OR capability-native) goes through in the real
`create_agent` loop. `test_native_capability_tool_gets_kpi_and_audit_coverage`
below is the explicit regression test for the bug this middleware fixes: a
plain `@tool`-decorated function, never wrapped by `ContextAwareTool`, now
gets the same KPI timer + audit events an MCP tool call gets.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, List, cast

import pytest
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from fred_sdk.contracts.context import (
    RuntimeContext as PortableRuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

# ---------------------------------------------------------------------------
# Shared fakes/fixtures (mirrors test_context_aware_tool.py's established
# pattern for stubbing the KPI writer and capturing the audit logger — reused
# here rather than inventing a new fixture style).
# ---------------------------------------------------------------------------


class _RecordingKPIStore(BaseKPIStore):
    """Minimal BaseKPIStore that just remembers every emitted event."""

    def __init__(self) -> None:
        self.events: List[KPIEvent] = []

    def ensure_ready(self) -> None:
        return

    def index_event(self, event: KPIEvent) -> None:
        self.events.append(event)

    def bulk_index(self, events: List[KPIEvent]) -> None:
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        return KPIQueryResult(rows=[])


def _install_recording_kpi_writer() -> tuple[_RecordingKPIStore, KPIWriter]:
    store = _RecordingKPIStore()
    return store, KPIWriter(store=store)


def _latency_event(store: _RecordingKPIStore) -> KPIEvent:
    matches = [
        e for e in store.events if e.metric and e.metric.name == "agent.tool_latency_ms"
    ]
    assert len(matches) == 1
    return matches[0]


def _failed_events(store: _RecordingKPIStore) -> List[KPIEvent]:
    return [
        e
        for e in store.events
        if e.metric and e.metric.name == "agent.tool_failed_total"
    ]


class _AuditEvents:
    """Captures every record emitted on the fred.security.audit logger."""

    def __init__(self) -> None:
        self.records: List[logging.LogRecord] = []

    def __enter__(self) -> "_AuditEvents":
        self._logger = logging.getLogger(AUDIT_LOGGER_NAME)
        self._previous_handlers = list(self._logger.handlers)
        self._previous_propagate = self._logger.propagate
        self._logger.handlers.clear()
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)

        owner = self

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                owner.records.append(record)

        self._logger.addHandler(_Capture())
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._logger.handlers.clear()
        for h in self._previous_handlers:
            self._logger.addHandler(h)
        self._logger.propagate = self._previous_propagate

    def event_names(self) -> list[str]:
        return [r.audit_event for r in self.records]  # type: ignore[attr-defined]


def _binding(*, baggage: dict[str, str] | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=PortableRuntimeContext(),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
            session_id="session-1",
            user_id="user-1",
            team_id="team-1",
            baggage=baggage or {},
        ),
    )


def _request(
    *, name: str, tool_obj: BaseTool | None, args: dict[str, Any] | None = None
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": "call-1"},
        tool=tool_obj,
        state={"messages": []},
        runtime=cast(Any, None),
    )


# ---------------------------------------------------------------------------
# Success / failure / cancellation semantics (ported from
# test_context_aware_tool.py's removed KPI/audit tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_awrap_tool_call_success_leaves_default_ok_status() -> None:
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(
        name="fake.search", tool_obj=None, args={"question": "secret-arg"}
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="fake.search", tool_call_id="call-1")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.content == "ok"
    assert _latency_event(store).dims["status"] == "ok"


@pytest.mark.asyncio
async def test_awrap_tool_call_raised_exception_sets_error_status_failed_counter_and_reraises() -> (
    None
):
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.failing", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await middleware.awrap_tool_call(request, handler)

    assert _latency_event(store).dims["status"] == "error"
    failed = _failed_events(store)
    assert len(failed) == 1
    assert failed[0].dims["error_code"] == "RuntimeError"


@pytest.mark.asyncio
async def test_awrap_tool_call_tool_message_error_status_marks_failed_without_raising() -> (
    None
):
    """LangChain's own `ToolNode` already converts a caught tool exception into
    `ToolMessage(status="error")` before `handler(request)` returns — this is
    the common path for capability-native tools (see the module docstring's
    "Known gap" note for why MCP tools via `ContextAwareTool` behave
    differently). No exception propagates here; only `.status` signals it."""
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.native", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="Error: boom",
            name="fake.native",
            tool_call_id="call-1",
            status="error",
        )

    with _AuditEvents() as audit:
        result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert _latency_event(store).dims["status"] == "error"
    assert len(_failed_events(store)) == 1
    assert audit.records[1].outcome == "failed"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_awrap_tool_call_cancelled_emits_cancelled_and_reraises() -> None:
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.cancelling", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        raise asyncio.CancelledError

    with _AuditEvents() as audit:
        with pytest.raises(asyncio.CancelledError):
            await middleware.awrap_tool_call(request, handler)

    assert _latency_event(store).dims["status"] == "cancelled"
    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]
    assert audit.records[1].outcome == "cancelled"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_awrap_tool_call_command_result_counts_as_succeeded() -> None:
    """A `Command` has no `.status` attribute — LangGraph already ran the tool
    and chose to redirect graph state, which is not a failure signal."""
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.command", tool_obj=None)

    command = Command(update={"messages": []})

    async def handler(req: ToolCallRequest) -> Command:
        return command

    with _AuditEvents() as audit:
        result = await middleware.awrap_tool_call(request, handler)

    assert result is command
    assert _latency_event(store).dims["status"] == "ok"
    assert audit.records[1].outcome == "succeeded"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_awrap_tool_call_emits_started_and_completed_audit_without_content_leak() -> (
    None
):
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(
        name="fake.search", tool_obj=None, args={"question": "very-secret-value"}
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="very-secret-result",
            name="fake.search",
            tool_call_id="call-1",
        )

    with _AuditEvents() as audit:
        await middleware.awrap_tool_call(request, handler)

    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]
    completed = audit.records[1]
    assert completed.outcome == "succeeded"  # type: ignore[attr-defined]
    assert completed.tool_name == "fake.search"  # type: ignore[attr-defined]
    # Privacy: no tool arguments or results anywhere in the audit payload.
    assert "very-secret-value" not in str(vars(completed))
    assert "very-secret-result" not in str(vars(completed))


@pytest.mark.asyncio
async def test_awrap_tool_call_without_kpi_writer_still_emits_audit() -> None:
    """KPI emission is a no-op when `kpi` is None (mirrors
    `TracingKpiMiddleware`'s own `kpi is None` handling) — the audit trail
    must still fire regardless."""
    middleware = ToolObservabilityMiddleware(kpi=None, binding=_binding())
    request = _request(name="fake.search", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="fake.search", tool_call_id="call-1")

    with _AuditEvents() as audit:
        result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]


# ---------------------------------------------------------------------------
# source dim: mcp vs capability
# ---------------------------------------------------------------------------


class _FakeMcpBaseTool(BaseTool):
    name: str = "fake.mcp.search"
    description: str = "Underlying tool ContextAwareTool would wrap."

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "ok"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return "ok"


class _FakeAgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


def _fake_context_aware_tool() -> ContextAwareTool:
    return ContextAwareTool(
        base_tool=_FakeMcpBaseTool(),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )


@tool
def native_capability_tool(question: str) -> str:
    """A plain capability-native tool, shaped exactly like
    `DocumentAccessCapability`'s `search_documents_using_vectorization` —
    NOT wrapped by `ContextAwareTool` at all."""
    return f"hits for {question}"


@pytest.mark.asyncio
async def test_source_dim_is_mcp_for_context_aware_tool() -> None:
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.mcp.search", tool_obj=_fake_context_aware_tool())

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="fake.mcp.search", tool_call_id="call-1")

    await middleware.awrap_tool_call(request, handler)

    assert _latency_event(store).dims["source"] == "mcp"


@pytest.mark.asyncio
async def test_native_capability_tool_gets_kpi_and_audit_coverage() -> None:
    """The whole point of #2011: before this middleware, a capability-native
    tool (never wrapped by `ContextAwareTool`) produced ZERO
    `agent.tool_latency_ms` samples and ZERO `agent.tool.invocation.*` audit
    events. It now gets exactly the same KPI timer + audit events an
    MCP-sourced tool call gets, just with `source="capability"` instead of
    `source="mcp"`."""
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())

    # Not a ContextAwareTool — exactly the shape a capability middleware ships
    # (`self.tools = [native_capability_tool]` on its own AgentMiddleware).
    assert not isinstance(native_capability_tool, ContextAwareTool)
    request = _request(
        name=native_capability_tool.name,
        tool_obj=native_capability_tool,
        args={"question": "what is fred"},
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        # Simulates what ToolNode would do after actually invoking the tool.
        return ToolMessage(
            content="hits for what is fred",
            name=native_capability_tool.name,
            tool_call_id="call-1",
        )

    with _AuditEvents() as audit:
        result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)

    latency = _latency_event(store)
    assert latency.dims["source"] == "capability"
    assert latency.dims["tool_name"] == native_capability_tool.name
    assert latency.dims["status"] == "ok"

    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]
    assert audit.records[0].source == "capability"  # type: ignore[attr-defined]
    assert audit.records[1].outcome == "succeeded"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _base_dims: identifiers only, sourced from BoundRuntimeContext
# ---------------------------------------------------------------------------


def test_base_dims_includes_identifiers_from_portable_context_and_baggage() -> None:
    middleware = ToolObservabilityMiddleware(
        kpi=None,
        binding=_binding(
            baggage={
                "agent_instance_id": "instance-1",
                "template_agent_id": "template-1",
            }
        ),
    )

    dims = middleware._base_dims(tool_name="fake.search", source="capability")

    assert dims["tool_name"] == "fake.search"
    assert dims["source"] == "capability"
    assert dims["session_id"] == "session-1"
    assert dims["user_id"] == "user-1"
    assert dims["team_id"] == "team-1"
    assert dims["agent_instance_id"] == "instance-1"
    assert dims["template_agent_id"] == "template-1"
    assert dims["correlation_id"] == "correlation-1"
