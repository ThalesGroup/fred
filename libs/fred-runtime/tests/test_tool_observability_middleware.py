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
import pytest_asyncio
from conftest import (
    RecordingSpan as _RecordingSpan,
)
from conftest import (
    RecordingTracer as _RecordingTracer,
)
from conftest import ToolFriendlyFakeChatModel
from deepagents.backends import StateBackend
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME
from fred_core.portable import Span
from fred_core.security.delegation import DelegationConfig
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    set_delegation_runtime,
)
from fred_runtime.deep.deep_runtime import (
    _build_deepagent_runtime_middleware,
    _create_compiled_deep_agent,
)
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.react.middleware.tool_call_recovery import (
    ToolCallTextRecoveryMiddleware,
)
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.react.react_tool_binding import SELF_TRACED_TOOL_METADATA_KEY
from fred_runtime.react.react_tracing import active_agent_span
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeContext,
    get_runtime_context,
    set_runtime_context,
)
from fred_runtime.runtime_support.authority import AuthorityLostError, RunStopError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.capability import ToolCarrierMiddleware
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    ToolInvocationResult,
)
from fred_sdk.contracts.context import (
    RuntimeContext as PortableRuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef, ToolApprovalPolicy
from langchain.agents import create_agent
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding


@pytest.fixture(autouse=True)
def _delegated_logging_context():
    set_delegation_runtime(
        DelegationRuntime(config=DelegationConfig(act_for_people=True))
    )
    try:
        yield
    finally:
        set_delegation_runtime(None)


@pytest_asyncio.fixture(autouse=True)
async def tool_authority():
    authority = TurnAuthority(
        turn_binding("template", user="user-1", session="session-1"), None
    )
    with RunScope.open() as scope:
        authority.start(scope)
        scope.turn_authority = authority
        yield authority


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

    def payload_text(self) -> str:
        return repr(
            [
                {**record.__dict__, "message": record.getMessage()}
                for record in self.records
            ]
        )


def _binding(*, baggage: dict[str, str] | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=PortableRuntimeContext(
            user_id="user-1",
            session_id="session-1",
            space_id=SPACE_ID,
            agent_instance_id=INSTANCE_ID,
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
            session_id="session-1",
            user_id="user-1",
            team_id="team-1",
            agent_id="template",
            baggage={
                "space_id": SPACE_ID,
                "agent_instance_id": INSTANCE_ID,
                "template_agent_id": "template",
                **(baggage or {}),
            },
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
async def test_oversized_unknown_tool_name_returns_the_tool_error_to_the_model() -> (
    None
):
    _, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    looped = "loop text " * 650 + ">>> read_document"
    request = _request(name=looped, tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content=f"Error: {looped} is not a valid tool",
            name=looped,
            tool_call_id="call-1",
            status="error",
        )

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage) and result.status == "error"


@pytest.mark.asyncio
async def test_awrap_tool_call_raised_exception_sets_error_status_failed_counter_and_reraises(
    caplog,
) -> None:
    from fred_core.logs.processors import install_context_capture

    install_context_capture()
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="identifier-tool-canary", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("upstream-error-canary")

    with caplog.at_level(
        logging.DEBUG,
        logger="fred_runtime.runtime_support.tool_execution",
    ):
        with pytest.raises(RuntimeError):
            await middleware.awrap_tool_call(request, handler)

    assert _latency_event(store).dims["status"] == "error"
    failed = _failed_events(store)
    assert len(failed) == 1
    assert failed[0].dims["error_code"] == "RuntimeError"
    emitted = repr(
        [
            {**record.__dict__, "message": record.getMessage()}
            for record in caplog.records
        ]
    )
    assert "identifier-tool-canary" not in caplog.text
    completed = next(r for r in caplog.records if r.msg == "Tool invocation completed")
    assert (
        getattr(completed, "_fred_snapshot").values["tool_name"]
        == "identifier-tool-canary"
    )
    assert "upstream-error-canary" not in emitted


@pytest.mark.asyncio
async def test_awrap_tool_call_terminal_stop_logs_only_bounded_reason(caplog) -> None:
    middleware = ToolObservabilityMiddleware(kpi=None, binding=_binding())
    request = _request(name="terminal-tool-canary", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        try:
            raise RuntimeError("terminal-upstream-canary")
        except RuntimeError as upstream:
            raise AuthorityLostError() from upstream

    with caplog.at_level(
        logging.DEBUG,
        logger="fred_runtime.runtime_support.tool_execution",
    ):
        with pytest.raises(AuthorityLostError):
            await middleware.awrap_tool_call(request, handler)

    emitted = repr(
        [
            {**record.__dict__, "message": record.getMessage()}
            for record in caplog.records
        ]
    )
    assert "reason=authority_lost" in emitted
    assert "terminal-tool-canary" not in caplog.text
    assert "terminal-upstream-canary" not in emitted


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
async def test_awrap_tool_call_is_error_artifact_marks_failed() -> None:
    """A tool that handles its own failure and returns an `is_error=True`
    artifact is still a failure.

    `_document_tool_failure` (document_access) deliberately RETURNS rather than
    raising, so LangChain never stamps `status="error"`. Before this was
    handled, such a call was audited `outcome="succeeded"` and never counted in
    `agent.tool_failed_total`, while `react_runtime` showed the very same step
    as failed in the user's trace.
    """

    class _Artifact:
        is_error = True

    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.native", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="Could not search documents: HTTP 401",
            name="fake.native",
            tool_call_id="call-1",
            artifact=_Artifact(),
        )

    with _AuditEvents() as audit:
        result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "success"  # LangChain's own view is unchanged
    assert _latency_event(store).dims["status"] == "error"
    failed = _failed_events(store)
    assert len(failed) == 1
    # The LABEL VALUES, not just the fact of a failure. `error_code` is what a
    # Grafana panel groups by, and `exception_type` must be present even though
    # nothing was raised: PrometheusKPIStore freezes a metric's label-name
    # tuple on its FIRST sample, so a handled failure arriving first would
    # otherwise drop `exception_type` from every raised failure thereafter.
    assert failed[0].dims["error_code"] == "tool_error_artifact"
    assert failed[0].dims["exception_type"] == "none"
    # And NOT on the latency histogram. Writing them there looks like richer
    # telemetry and delivers none: the first `agent.tool_latency_ms` sample in a
    # pod is a success carrying neither dim, and PrometheusKPIStore pins the
    # label-name tuple to that first sample — so every later `error_code` on
    # this metric is discarded before export. Asserting their ABSENCE keeps the
    # code honest about what Grafana actually receives.
    latency_dims = _latency_event(store).dims
    assert "error_code" not in latency_dims
    assert "exception_type" not in latency_dims
    assert audit.records[1].outcome == "failed"  # type: ignore[attr-defined]
    assert audit.records[1].reason == "tool_error_artifact"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_awrap_tool_call_dict_is_error_artifact_marks_failed() -> None:
    """A dict artifact counts too.

    `normalize_tool_artifact` (react_stream_adapter) model_validates a dict into
    a `ToolInvocationResult`, so a dict-returning tool shows as failed in the
    user's trace. An attribute-only check here would have recorded that same
    call as a success.
    """
    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.native", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="boom",
            name="fake.native",
            tool_call_id="call-1",
            artifact={"is_error": True},
        )

    with _AuditEvents() as audit:
        await middleware.awrap_tool_call(request, handler)

    assert len(_failed_events(store)) == 1
    assert audit.records[1].outcome == "failed"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_awrap_tool_call_success_artifact_stays_succeeded() -> None:
    """The artifact check must not turn ordinary successes into failures."""

    class _Artifact:
        is_error = False

    store, kpi = _install_recording_kpi_writer()
    middleware = ToolObservabilityMiddleware(kpi=kpi, binding=_binding())
    request = _request(name="fake.native", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="ok",
            name="fake.native",
            tool_call_id="call-1",
            artifact=_Artifact(),
        )

    with _AuditEvents() as audit:
        await middleware.awrap_tool_call(request, handler)

    assert len(_failed_events(store)) == 0
    assert audit.records[1].outcome == "succeeded"  # type: ignore[attr-defined]


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
    assert completed.reason == "tool_completed"  # type: ignore[attr-defined]
    # Every emitted field is checked: identifiers, arguments and results are
    # absent from both LogRecord extras and its formatted message.
    for canary in (
        "fake.search",
        "call-1",
        "request-1",
        "correlation-1",
        "session-1",
        "user-1",
        "team-1",
        "very-secret-value",
        "very-secret-result",
    ):
        assert canary not in audit.payload_text()


@pytest.mark.asyncio
async def test_flag_off_preserves_legacy_audit_dimensions() -> None:
    set_delegation_runtime(None)
    middleware = ToolObservabilityMiddleware(kpi=None, binding=_binding())
    request = _request(name="legacy.tool", tool_obj=None)

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="legacy.tool", tool_call_id="call-1")

    with _AuditEvents() as audit:
        await middleware.awrap_tool_call(request, handler)

    started, completed = audit.records
    assert started.tool_name == "legacy.tool"  # type: ignore[attr-defined]
    assert completed.tool_name == "legacy.tool"  # type: ignore[attr-defined]
    assert completed.outcome == "succeeded"  # type: ignore[attr-defined]


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
    `DocumentAccessCapability`'s `search_documents` —
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
    assert audit.records[1].outcome == "succeeded"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _base_dims: identifiers only, sourced from BoundRuntimeContext
# ---------------------------------------------------------------------------


class _FakeRebacEngine:
    """Reject any attempt to reintroduce Swift authority reads during a turn."""

    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def check_permission_or_raise(
        self, subject: Any, permission: Any, resource: Any, **_: Any
    ) -> None:
        self.calls.append((subject.id, resource.id))
        raise AssertionError(
            "Tool execution must use the admitted Weaver turn, not Swift ReBAC"
        )


def _with_rebac_engine(engine: _FakeRebacEngine | None):
    """Context manager installing a fake pod-wide RuntimeContext for the
    duration of one test, restoring whatever was there before on exit — the
    global is process-wide (`set_runtime_context`), so tests must not leak it."""

    class _Ctx:
        def __enter__(self) -> None:
            try:
                self._previous: RuntimeContext | None = get_runtime_context()
            except RuntimeError:
                self._previous = None
            set_runtime_context(
                RuntimeContext(
                    RuntimeConfig(
                        knowledge_flow_url="http://kf.invalid",
                        rebac_engine=engine,
                    )
                )
            )

        def __exit__(self, *exc_info: object) -> None:
            set_runtime_context(self._previous)

    return _Ctx()


@pytest.mark.asyncio
async def test_tools_share_admitted_authority_without_swift_rechecks() -> None:
    engine = _FakeRebacEngine()
    middleware = ToolObservabilityMiddleware(kpi=None, binding=_binding())
    calls = 0

    async def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(content="ok", tool_call_id="call-1")

    with _with_rebac_engine(engine):
        for _ in range(2):
            await middleware.awrap_tool_call(
                _request(name="search", tool_obj=None), handler
            )
        await asyncio.create_task(
            middleware.awrap_tool_call(_request(name="search", tool_obj=None), handler)
        )
    assert calls == 3
    assert engine.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,field",
    [
        ("portable", "user_id"),
        ("portable", "session_id"),
        ("portable", "agent_id"),
        ("portable", "space_id"),
        ("portable", "agent_instance_id"),
        ("runtime", "user_id"),
        ("runtime", "session_id"),
        ("runtime", "space_id"),
        ("runtime", "agent_instance_id"),
    ],
)
async def test_tool_refuses_context_outside_admitted_turn(
    surface: str, field: str
) -> None:
    binding = _binding()
    if surface == "portable":
        portable = binding.portable_context
        update = (
            {"baggage": {**portable.baggage, field: "another"}}
            if field in {"space_id", "agent_instance_id"}
            else {field: "another"}
        )
        binding = BoundRuntimeContext(
            runtime_context=binding.runtime_context,
            portable_context=portable.model_copy(update=update),
        )
    else:
        binding = BoundRuntimeContext(
            runtime_context=binding.runtime_context.model_copy(
                update={field: "another"}
            ),
            portable_context=binding.portable_context,
        )
    middleware = ToolObservabilityMiddleware(kpi=None, binding=binding)

    async def handler(request: ToolCallRequest) -> ToolMessage:
        raise AssertionError("Mismatched tool context must not execute")

    with _AuditEvents() as audit, pytest.raises(AuthorityLostError):
        await middleware.awrap_tool_call(
            _request(name="search", tool_obj=None), handler
        )
    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]
    assert getattr(audit.records[-1], "outcome") == "failed"


@pytest.mark.asyncio
async def test_recovered_call_uses_admitted_turn_before_fake_tool_invocation() -> None:
    engine = _FakeRebacEngine()
    recovery = ToolCallTextRecoveryMiddleware()
    model_response = ModelResponse(
        result=[
            AIMessage(
                content=[
                    {"type": "text", "text": native_capability_tool.name},
                    {"type": "reference", "reference_ids": []},
                    {"type": "text", "text": '{"question":"what is fred"}'},
                ],
                response_metadata={"model_name": "mistral-medium-latest"},
            )
        ]
    )

    async def model_handler(_: ModelRequest) -> ModelResponse:
        return model_response

    normalized = await recovery.awrap_model_call(
        ModelRequest(
            model=cast(Any, None), messages=[], tools=[native_capability_tool]
        ),
        model_handler,
    )
    message = normalized.result[0]
    assert isinstance(message, AIMessage)
    (call,) = message.tool_calls
    middleware = ToolObservabilityMiddleware(kpi=None, binding=_binding())
    request = ToolCallRequest(
        tool_call=call,
        tool=native_capability_tool,
        state={"messages": [message]},
        runtime=cast(Any, None),
    )
    handler_called = False

    async def handler(req: ToolCallRequest) -> ToolMessage:
        nonlocal handler_called
        assert engine.calls == []
        handler_called = True
        return ToolMessage(
            content="fake result",
            name=req.tool_call["name"],
            tool_call_id=req.tool_call["id"],
        )

    with _with_rebac_engine(engine):
        result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert handler_called is True
    assert engine.calls == []
    assert result.tool_call_id == call["id"]


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

    dims = middleware._execution._base_dims(
        tool_name="fake.search", source="capability"
    )

    assert dims["tool_name"] == "fake.search"
    assert dims["source"] == "capability"
    assert dims["session_id"] == "session-1"
    assert dims["user_id"] == "user-1"
    assert dims["team_id"] == "team-1"
    assert dims["agent_instance_id"] == "instance-1"
    assert dims["template_agent_id"] == "template-1"
    assert dims["correlation_id"] == "correlation-1"


# ---------------------------------------------------------------------------
# Trace spans for tools the ReAct binder never sees
# ---------------------------------------------------------------------------


def _self_traced_tool() -> BaseTool:
    """Shaped like what `ReActToolBinder` hands to `create_agent`."""

    async def _run(question: str) -> str:
        return "ok"

    return StructuredTool.from_function(
        func=None,
        coroutine=_run,
        name="declared.search",
        description="A binder-bound tool.",
        metadata={SELF_TRACED_TOOL_METADATA_KEY: True},
    )


@pytest.mark.asyncio
async def test_capability_tool_call_gets_a_trace_span() -> None:
    tracer = _RecordingTracer()
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )
    request = _request(
        name="native_capability_tool", tool_obj=cast(Any, native_capability_tool)
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="ok", name="native_capability_tool", tool_call_id="call-1"
        )

    await middleware.awrap_tool_call(request, handler)

    assert len(tracer.spans) == 1
    name, attributes, span = tracer.spans[0]
    assert name == "v2.react.runtime_tool"
    assert attributes["tool_name"] == "native_capability_tool"
    assert span.attributes["status"] == "ok"
    assert span.ended is True


@pytest.mark.asyncio
async def test_binder_bound_tool_is_not_spanned_twice() -> None:
    tracer = _RecordingTracer()
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )
    request = _request(name="declared.search", tool_obj=_self_traced_tool())

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", name="declared.search", tool_call_id="call-1")

    await middleware.awrap_tool_call(request, handler)

    assert tracer.spans == []


@pytest.mark.asyncio
async def test_failing_capability_tool_ends_its_span_as_an_error() -> None:
    tracer = _RecordingTracer()
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )
    request = _request(
        name="native_capability_tool", tool_obj=cast(Any, native_capability_tool)
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await middleware.awrap_tool_call(request, handler)

    _, _, span = tracer.spans[0]
    assert span.attributes["status"] == "error"
    assert span.attributes["error_type"] == "RuntimeError"
    assert span.ended is True


@pytest.mark.asyncio
async def test_tool_span_parents_on_the_turn_and_hosts_the_child_turn() -> None:
    """The orphaned-sub-agent bug in two assertions.

    The tool span must hang under the turn's own span, and must itself be the
    active parent while the tool runs — that is what makes a `native_capability_tool`
    child's root span nest inside the call that opened it instead of landing
    beside its parent as a second root.
    """

    tracer = _RecordingTracer()
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )
    turn_span = _RecordingSpan()
    token = active_agent_span.set(turn_span)
    seen_inside: list[Span | None] = []

    async def handler(req: ToolCallRequest) -> ToolMessage:
        seen_inside.append(active_agent_span.get())
        return ToolMessage(
            content="ok", name="native_capability_tool", tool_call_id="call-1"
        )

    try:
        await middleware.awrap_tool_call(
            _request(
                name="native_capability_tool",
                tool_obj=cast(Any, native_capability_tool),
            ),
            handler,
        )
        restored = active_agent_span.get()
    finally:
        active_agent_span.reset(token)

    _, _, tool_span_obj = tracer.spans[0]
    assert tracer.parents == [turn_span]
    assert seen_inside == [tool_span_obj]
    assert restored is turn_span


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [False, True])
async def test_capability_trace_content_is_opt_in(capture: bool) -> None:
    tracer = _RecordingTracer(capture=capture)
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="private-result", tool_call_id="call-1")

    await middleware.awrap_tool_call(
        _request(name="search", tool_obj=None, args={"question": "private-argument"}),
        handler,
    )
    span = tracer.spans[0][2]
    assert span.io == (
        [
            {"input": {"question": "private-argument"}, "output": None},
            {"input": None, "output": "private-result"},
        ]
        if capture
        else []
    )


@pytest.mark.asyncio
async def test_cancelled_capability_span_ends_and_restores_parent() -> None:
    tracer = _RecordingTracer()
    parent = _RecordingSpan()
    token = active_agent_span.set(parent)
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        raise asyncio.CancelledError

    try:
        with pytest.raises(asyncio.CancelledError):
            await middleware.awrap_tool_call(
                _request(name="search", tool_obj=None), handler
            )
        assert active_agent_span.get() is parent
    finally:
        active_agent_span.reset(token)
    span = tracer.spans[0][2]
    assert span.ended
    assert span.attributes["status"] == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,artifact,error_type",
    [
        ("error", None, "tool_error_status"),
        ("success", {"is_error": True}, "tool_error_artifact"),
    ],
)
async def test_returned_capability_error_marks_trace(
    status: str, artifact: Any, error_type: str
) -> None:
    tracer = _RecordingTracer()
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )

    async def handler(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="failed",
            tool_call_id="call-1",
            status=cast(Any, status),
            artifact=artifact,
        )

    await middleware.awrap_tool_call(_request(name="search", tool_obj=None), handler)
    span = tracer.spans[0][2]
    assert span.ended
    assert span.attributes == {"status": "error", "error_type": error_type}


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["react", "deep"])
async def test_compiled_runtime_traces_capability_tool(runtime: str) -> None:
    tracer = _RecordingTracer()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "native_capability_tool",
                        "args": {"question": "hello"},
                        "id": "call-1",
                    }
                ],
            ),
            AIMessage(content="finished"),
        ]
    )
    carrier = ToolCarrierMiddleware([native_capability_tool], capability_id="test")
    if runtime == "deep":
        middleware = _build_deepagent_runtime_middleware(
            tracer=tracer,
            kpi=None,
            binding=_binding(),
            approval_policy=ToolApprovalPolicy(),
            available_tool_names={"native_capability_tool"},
        )
        agent = _create_compiled_deep_agent(
            model=model,
            tools=[],
            system_prompt="Use the tool.",
            checkpointer=None,
            subagent_middleware=[],
            middleware=[carrier, *middleware],
            backend=StateBackend(),
            permissions=[],
        )
    else:
        agent = create_agent(
            model=model,
            tools=[],
            middleware=[
                carrier,
                ToolObservabilityMiddleware(
                    kpi=None, binding=_binding(), tracer=tracer
                ),
            ],
        )
    parent = _RecordingSpan()
    token = active_agent_span.set(parent)
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "hello"}]}
        )
        assert active_agent_span.get() is parent
    finally:
        active_agent_span.reset(token)
    tool_indices = [
        i
        for i, (name, _, _) in enumerate(tracer.spans)
        if name == "v2.react.runtime_tool"
    ]
    assert len(tool_indices) == 1
    index = tool_indices[0]
    assert tracer.parents[index] is parent
    assert tracer.spans[index][2].ended
    assert result["messages"][-1].content == "finished"


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [False, True])
async def test_command_trace_captures_only_matching_tool_result(capture: bool) -> None:
    tracer = _RecordingTracer(capture=capture)
    middleware = ToolObservabilityMiddleware(
        kpi=None, binding=_binding(), tracer=tracer
    )

    async def handler(req: ToolCallRequest) -> Command[Any]:
        return Command(
            update={
                "private_state": "not trace content",
                "messages": [
                    AIMessage(content="not a tool result"),
                    ToolMessage(content="other call", tool_call_id="other"),
                    ToolMessage(content="updated todos", tool_call_id="call-1"),
                ],
            }
        )

    await middleware.awrap_tool_call(
        _request(name="write_todos", tool_obj=None), handler
    )
    span = tracer.spans[0][2]
    assert span.io == (
        [
            {"input": {}, "output": None},
            {"input": None, "output": ["updated todos"]},
        ]
        if capture
        else []
    )
    assert span.ended


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "ended", "closed", "stopped"])
@pytest.mark.parametrize("service_agent", [False, True])
async def test_tool_requires_live_authority_even_for_service_agents(
    state: str, service_agent: bool, tool_authority: TurnAuthority
) -> None:
    scope = RunScope.current()
    assert scope is not None
    if state == "missing":
        scope.turn_authority = None
    elif state == "ended":
        tool_authority.close()
    elif state == "closed":
        scope.close()
    else:
        scope.record_stop(AuthorityLostError())
    middleware = ToolObservabilityMiddleware(
        kpi=None,
        binding=_binding(baggage={"is_service_agent": str(service_agent).lower()}),
    )

    async def handler(request: ToolCallRequest) -> ToolMessage:
        raise AssertionError("Tool must not run without active authority")

    with pytest.raises(RunStopError):
        await middleware.awrap_tool_call(
            _request(name="search", tool_obj=None), handler
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["react", "deep", "graph_runtime_tool", "graph_tool_ref"]
)
@pytest.mark.parametrize(
    "outcome", ["success", "reported_error", "raised", "cancelled", "denied"]
)
async def test_runtime_tool_guarantees_match(
    path: str, outcome: str, tool_authority: TurnAuthority
) -> None:
    """The real adapters authorize once, execute at most once and record one outcome."""
    from fred_core.portable import InMemoryMetricsProvider
    from fred_runtime.graph.node_context import NodeContext
    from fred_runtime.integrations.v2_runtime.adapters import InProcessToolInvoker
    from fred_sdk.contracts.context import ToolInvocationResult
    from fred_sdk.contracts.runtime import RuntimeServices

    store, kpi = _install_recording_kpi_writer()
    engine = _FakeRebacEngine()
    if outcome == "denied":
        tool_authority.close()
    executions = 0

    async def execute() -> ToolInvocationResult:
        nonlocal executions
        executions += 1
        assert engine.calls == []
        if outcome == "raised":
            raise ValueError("private failure detail")
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        return ToolInvocationResult(
            tool_ref="probe", is_error=outcome == "reported_error"
        )

    @tool("probe", response_format="content_and_artifact")
    async def probe() -> tuple[str, ToolInvocationResult]:
        """Exercise the same capability under each runtime."""
        return "private result", await execute()

    metrics = InMemoryMetricsProvider()
    if path.startswith("graph"):
        ctx = NodeContext(
            binding=_binding(),
            services=RuntimeServices(
                kpi_writer=kpi,
                metrics=metrics,
                tool_invoker=InProcessToolInvoker(
                    handlers={"probe": lambda _: execute()}
                ),
            ),
            model=None,
            graph_agent_id="graph",
            node_id="call",
            allowed_tool_refs=frozenset({"probe"}),
            runtime_tools={"probe": probe},
            tuning_values={},
            sink=lambda _: None,
        )

        async def invoke() -> object:
            if path == "graph_tool_ref":
                return await ctx.invoke_tool("probe", {})
            return await ctx.invoke_runtime_tool("probe", {})
    else:
        if path == "deep":
            frame = _build_deepagent_runtime_middleware(
                tracer=None,
                kpi=kpi,
                binding=_binding(),
                approval_policy=ToolApprovalPolicy(),
                available_tool_names={"probe"},
            )
            middleware = next(
                m for m in frame if isinstance(m, ToolObservabilityMiddleware)
            )
        else:
            from fred_runtime.react.middleware.frame import (
                build_react_platform_middleware_frame,
            )

            frame = build_react_platform_middleware_frame(
                tracer=None,
                kpi=kpi,
                binding=_binding(),
                approval_policy=ToolApprovalPolicy(),
                available_tool_names={"probe"},
                max_history_messages=None,
                max_history_chars=None,
                max_tool_calls_per_turn=None,
            )
            middleware = next(
                m for m in frame if isinstance(m, ToolObservabilityMiddleware)
            )
        request = _request(name="probe", tool_obj=probe)

        async def invoke() -> object:
            return await middleware.awrap_tool_call(
                request,
                lambda req: probe.ainvoke({**req.tool_call, "type": "tool_call"}),
            )

    expected_exception = {
        "denied": AuthorityLostError,
        "raised": ValueError,
        "cancelled": asyncio.CancelledError,
    }.get(outcome)
    with _with_rebac_engine(engine), _AuditEvents() as audit:
        if expected_exception is not None:
            with pytest.raises(expected_exception):
                await invoke()
        else:
            await invoke()
    assert executions == (0 if outcome == "denied" else 1)
    assert engine.calls == []
    assert audit.event_names() == [
        "agent.tool.invocation.started",
        "agent.tool.invocation.completed",
    ]
    expected_status = (
        "ok"
        if outcome == "success"
        else "cancelled"
        if outcome == "cancelled"
        else "error"
    )
    assert _latency_event(store).dims["status"] == expected_status
    assert getattr(audit.records[-1], "outcome") == (
        "succeeded"
        if outcome == "success"
        else "cancelled"
        if outcome == "cancelled"
        else "failed"
    )
    assert len(_failed_events(store)) == (
        0 if outcome in ("success", "cancelled") else 1
    )
    if outcome == "reported_error":
        assert _failed_events(store)[0].dims["error_code"] == "tool_error_artifact"
    assert not metrics.timers  # Graph no longer emits a second, generic tool timer.
    assert "private result" not in audit.payload_text()
    assert "private failure detail" not in audit.payload_text()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_graph_mcp_keeps_handled_failure_for_audit_kpi_and_event(
    fails: bool,
) -> None:
    from fred_runtime.graph.node_context import NodeContext
    from fred_sdk.contracts.runtime import RuntimeServices, ToolResultRuntimeEvent

    calls = 0

    @tool("mcp_probe", response_format="content_and_artifact")
    async def probe() -> tuple[str, None]:
        """An MCP server response, including caught failures."""
        nonlocal calls
        calls += 1
        if fails:
            raise ValueError("provider failed")
        return "ok", None

    wrapped = ContextAwareTool(
        base_tool=probe,
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )
    store, kpi = _install_recording_kpi_writer()
    events = []
    ctx = NodeContext(
        binding=_binding(),
        services=RuntimeServices(kpi_writer=kpi),
        model=None,
        graph_agent_id="graph",
        node_id="call",
        allowed_tool_refs=frozenset(),
        runtime_tools={wrapped.name: wrapped},
        tuning_values={},
        sink=events.append,
    )
    with _with_rebac_engine(_FakeRebacEngine()), _AuditEvents() as audit:
        await ctx.invoke_runtime_tool(wrapped.name, {})
    assert calls == 1
    assert _latency_event(store).dims["source"] == "mcp"
    assert _latency_event(store).dims["status"] == ("error" if fails else "ok")
    assert len(_failed_events(store)) == int(fails)
    assert len(audit.records) == 2
    assert getattr(audit.records[-1], "outcome") == ("failed" if fails else "succeeded")
    results = [event for event in events if isinstance(event, ToolResultRuntimeEvent)]
    assert len(results) == 1
    assert results[0].is_error == fails
