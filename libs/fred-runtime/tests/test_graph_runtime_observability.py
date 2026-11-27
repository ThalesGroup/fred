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

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest
from fred_core.portable import InMemoryMetricsProvider, Span, Tracer
from fred_runtime.graph.node_context import (
    NodeContext,
    _graph_phase_timer,
    _observe,
    _start_runtime_span,
)
from fred_runtime.integrations.v2_runtime.adapters import (
    CompositeToolInvoker,
    InProcessToolInvoker,
)
from fred_runtime.runtime_support.tool_approval import ToolApproval
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import (
    RuntimeEvent,
    RuntimeServices,
    ToolCallRuntimeEvent,
    ToolInvokerPort,
)
from fred_sdk.support.builtins import (
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint
from langgraph.types import Command


class _RecordingSpan(Span):
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.ended = False

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True


class _RecordingTracer(Tracer):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: Span | None = None,
        **kwargs: object,
    ) -> Span:
        del parent
        span = _RecordingSpan()
        self.calls.append(
            {
                "name": name,
                "context": context,
                "attributes": dict(attributes or {}),
                "span": span,
            }
        )
        return span


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="sess-1",
            user_id="alice",
            team_id="team-red",
            trace_id="trace-1",
            correlation_id="corr-1",
            agent_instance_id="inst-1",
            template_agent_id="template-1",
            execution_action="resume",
        ),
        portable_context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            trace_id="trace-1",
            agent_id="template-1",
            agent_name="template-1",
            session_id="sess-1",
            user_id="alice",
            team_id="team-red",
            baggage={
                "agent_instance_id": "inst-1",
                "template_agent_id": "template-1",
                "execution_action": "resume",
            },
        ),
    )


def test_graph_phase_timer_includes_managed_observability_dims() -> None:
    metrics = InMemoryMetricsProvider()
    binding = _binding()

    with _graph_phase_timer(
        metrics=metrics,
        binding=binding,
        agent_id="template-1",
        phase="graph_turn",
        agent_step="execute",
    ):
        pass

    assert len(metrics.timers) == 1
    dims = metrics.timers[0].dims
    assert dims["user_id"] == "alice"
    assert dims["team_id"] == "team-red"
    assert dims["session_id"] == "sess-1"
    assert dims["agent_instance_id"] == "inst-1"
    assert dims["template_agent_id"] == "template-1"
    assert "checkpoint_id" not in dims
    assert dims["trace_id"] == "trace-1"
    assert dims["correlation_id"] == "corr-1"
    assert dims["execution_action"] == "resume"


def test_start_runtime_span_includes_managed_observability_attrs() -> None:
    tracer = _RecordingTracer()
    binding = _binding()

    span = _start_runtime_span(
        services=RuntimeServices(tracer=tracer),
        binding=binding,
        name="agent.run",
        attributes={"status": "ok"},
    )

    assert span is not None
    assert len(tracer.calls) == 1
    attrs = cast(dict[str, object], tracer.calls[0]["attributes"])
    assert attrs["status"] == "ok"
    assert attrs["user_id"] == "alice"
    assert attrs["team_id"] == "team-red"
    assert attrs["session_id"] == "sess-1"
    assert attrs["agent_instance_id"] == "inst-1"
    assert attrs["template_agent_id"] == "template-1"
    assert "checkpoint_id" not in attrs
    assert attrs["trace_id"] == "trace-1"
    assert attrs["correlation_id"] == "corr-1"
    assert attrs["execution_action"] == "resume"


def _observed_context() -> tuple[
    NodeContext, _RecordingTracer, InMemoryMetricsProvider
]:
    tracer = _RecordingTracer()
    metrics = InMemoryMetricsProvider()
    context = NodeContext(
        binding=_binding(),
        services=RuntimeServices(tracer=tracer, metrics=metrics),
        model=None,
        graph_agent_id="template-1",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools={},
        tuning_values={},
        sink=lambda _event: None,
    )
    return context, tracer, metrics


@pytest.mark.asyncio
async def test_graph_builtin_resumes_legacy_tool_ref_with_canonical_name() -> None:
    events: list[RuntimeEvent] = []
    context = NodeContext(
        binding=_binding(),
        services=RuntimeServices(),
        model=None,
        graph_agent_id="template-1",
        node_id="node-1",
        allowed_tool_refs=frozenset({TOOL_REF_GEO_RENDER_POINTS}),
        runtime_tools={},
        tuning_values={},
        sink=events.append,
        checkpoint_tools=True,
        tool_approval=ToolApproval(
            approval_policy=ToolApprovalPolicy(
                enabled=True, always_require_tools=("geo.render_points",)
            )
        ),
    )

    @entrypoint(checkpointer=InMemorySaver())
    async def call_tool(tool_ref: str) -> str:
        result = await context.invoke_tool(
            tool_ref, {"points": [{"latitude": 1, "longitude": 2}]}
        )
        assert result.ui_parts[0].type == "geo"
        return result.tool_ref

    config: RunnableConfig = {"configurable": {"thread_id": "legacy-graph-tool"}}
    paused = await call_tool.ainvoke("geo.render_points", config)
    assert paused["__interrupt__"]
    resumed = await call_tool.ainvoke(Command(resume="proceed"), config)

    assert resumed == TOOL_REF_GEO_RENDER_POINTS
    names = {
        event.tool_name for event in events if isinstance(event, ToolCallRuntimeEvent)
    }
    assert names == {TOOL_REF_GEO_RENDER_POINTS}


@pytest.mark.asyncio
@pytest.mark.parametrize("knows_registrations", [False, True])
async def test_graph_builtin_name_keeps_explicit_custom_registration(
    knows_registrations: bool,
) -> None:
    requests: list[ToolInvocationRequest] = []

    class CustomMapInvoker(ToolInvokerPort):
        async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
            requests.append(request)
            return ToolInvocationResult(tool_ref=request.tool_ref)

    unknown_invoker = CustomMapInvoker()
    invoker = (
        InProcessToolInvoker(
            handlers={TOOL_REF_GEO_RENDER_POINTS: unknown_invoker.invoke}
        )
        if knows_registrations
        else unknown_invoker
    )
    context, _, _ = _observed_context()
    context = replace(
        context,
        services=RuntimeServices(tool_invoker=invoker),
        allowed_tool_refs=frozenset({TOOL_REF_GEO_RENDER_POINTS}),
        declared_tool_refs=frozenset({TOOL_REF_GEO_RENDER_POINTS}),
    )
    custom = await context.invoke_tool(TOOL_REF_GEO_RENDER_POINTS, {"place": "Toulon"})
    points: dict[str, object] = {"points": [{"latitude": 43.12, "longitude": 5.93}]}
    builtin = await context.invoke_tool("geo.render_points", points)
    automatic = await replace(context, declared_tool_refs=frozenset()).invoke_tool(
        TOOL_REF_GEO_RENDER_POINTS, points
    )

    assert [request.tool_ref for request in requests] == [TOOL_REF_GEO_RENDER_POINTS]
    assert custom.ui_parts == ()
    assert builtin.ui_parts[0].type == automatic.ui_parts[0].type == "geo"


@pytest.mark.asyncio
async def test_graph_custom_declaration_cannot_authorize_colliding_builtin() -> None:
    def result(request: ToolInvocationRequest) -> ToolInvocationResult:
        return ToolInvocationResult(tool_ref=request.tool_ref)

    invoker = CompositeToolInvoker(
        handlers={TOOL_REF_KNOWLEDGE_SEARCH: result},
        fallback=InProcessToolInvoker(handlers={"knowledge.search": result}),
    )
    context, _, _ = _observed_context()
    context = replace(
        context,
        services=RuntimeServices(tool_invoker=invoker),
        allowed_tool_refs=frozenset({TOOL_REF_KNOWLEDGE_SEARCH}),
        declared_tool_refs=frozenset({TOOL_REF_KNOWLEDGE_SEARCH}),
    )
    with pytest.raises(RuntimeError, match="undeclared tool_ref"):
        await context.invoke_tool("knowledge.search", {"query": "x"})

    declared_legacy = replace(
        context, declared_tool_refs=frozenset({"knowledge.search"})
    )
    builtin = await declared_legacy.invoke_tool(
        TOOL_REF_KNOWLEDGE_SEARCH, {"query": "x"}
    )
    assert builtin.tool_ref == "knowledge.search"


def _only_span(tracer: _RecordingTracer) -> _RecordingSpan:
    (call,) = tracer.calls
    return cast(_RecordingSpan, call["span"])


def test_observe_marks_a_completed_call_ok() -> None:
    context, tracer, metrics = _observed_context()

    with _observe(
        context,
        "v2.graph.tool",
        {"tool_ref": "t"},
        phase="v2_graph_tool",
        dims={"tool_name": "t"},
    ):
        pass

    span = _only_span(tracer)
    assert span.ended and span.attributes["status"] == "ok"
    (timer,) = metrics.timers
    assert timer.dims["status"] == "ok"
    assert timer.dims["phase"] == "v2_graph_tool"
    assert timer.dims["agent_step"] == "node-1"
    assert timer.dims["node_id"] == "node-1"
    assert timer.dims["tool_name"] == "t"


def test_observe_marks_an_error_result_without_an_exception() -> None:
    context, tracer, metrics = _observed_context()

    with _observe(context, "v2.graph.tool", {}, phase="v2_graph_tool") as obs:
        obs.fail()

    assert _only_span(tracer).attributes["status"] == "error"
    assert metrics.timers[0].dims["status"] == "error"


def test_observe_marks_a_raising_call_and_still_ends_its_span() -> None:
    context, tracer, metrics = _observed_context()

    def failing_call() -> None:
        with _observe(context, "v2.graph.tool", {}, phase="v2_graph_tool"):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        failing_call()

    span = _only_span(tracer)
    assert span.ended and span.attributes["status"] == "error"
    assert metrics.timers[0].dims["status"] == "error"


def test_observe_without_a_phase_records_a_span_only() -> None:
    context, tracer, metrics = _observed_context()

    with _observe(context, "v2.graph.fs_write", {"path": "a.md"}):
        pass

    assert _only_span(tracer).attributes["status"] == "ok"
    assert metrics.timers == []
