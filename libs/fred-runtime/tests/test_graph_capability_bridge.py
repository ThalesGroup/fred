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

"""Native capability tools retain content, artifacts and identity in Graph."""

from __future__ import annotations

import asyncio
import json

import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.capabilities import (
    CapabilityAssemblyError,
    build_capability_context,
)
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.graph.graph_runtime import (
    _capability_tools,
)
from fred_runtime.graph.node_context import NodeContext
from fred_sdk.contracts.capability import CapabilityIdentity
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    RuntimeEvent,
    RuntimeServices,
    RuntimeToolHandle,
    ToolProviderPort,
    ToolResultRuntimeEvent,
)
from langchain_core.tools import tool as lc_tool


@lc_tool("corpus_search", response_format="content_and_artifact")
async def _corpus_search(question: str) -> tuple[str, ToolInvocationResult]:
    """A citing capability tool: JSON content, plus an artifact with sources.

    Stands in for the shape a real search capability returns (blocks AND
    sources), which the bridge must preserve; `tracer_echo` further down covers
    the other shape (ui_parts, no blocks). Local on purpose — fred-runtime's
    own tests never depend on a capability package.
    """

    hits = (
        VectorSearchHit(
            uid="d1", title="Doc", content="body", score=1.0, type="document"
        ),
    )
    # A JSON object, because `_normalize_runtime_tool_output` parses a content
    # string back into a dict.
    content = json.dumps({"query": question, "hits": [{"uid": hits[0].uid}]})
    artifact = ToolInvocationResult(
        tool_ref="corpus_search",
        blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data={"query": question}),),
        sources=hits,
    )
    return content, artifact


def _sourced_capability_tool():
    """The citing capability tool above, `response_format="content_and_artifact"`."""

    return _corpus_search


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
            team_id="t",
        ),
    )


def _node_context(
    runtime_tools,
    *,
    services: RuntimeServices | None = None,
    events: list[RuntimeEvent] | None = None,
) -> NodeContext:
    return NodeContext(
        binding=_binding(),
        services=services if services is not None else RuntimeServices(),
        model=None,
        graph_agent_id="graph-agent",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools=runtime_tools,
        tuning_values={},
        sink=events.append if events is not None else (lambda _event: None),
    )


# ---------------------------------------------------------------------------
# The empirical proof: sources survive the REAL invoke_runtime_tool path.
# ---------------------------------------------------------------------------


def test_capability_tool_sources_survive_invoke_runtime_tool() -> None:
    source_tool = _sourced_capability_tool()
    ctx = _node_context({source_tool.name: source_tool})

    result = asyncio.run(
        ctx.invoke_runtime_tool("corpus_search", {"question": "what is fred?"})
    )

    # `_normalize_runtime_tool_output` model_dumps the bare ToolInvocationResult
    # (no special-cased handling for it exists) — the dict still carries the
    # full `sources` payload, uid included.
    assert isinstance(result, dict)
    assert result["sources"][0]["uid"] == "d1"
    assert result["is_error"] is False


def test_capability_tool_answer_survives_invoke_runtime_tool() -> None:
    """A full capability keeps both textual content and its UI artifact."""
    from _tracer_capability import TracerEchoCapability
    from fred_runtime.capabilities import CapabilityRegistry

    cap = TracerEchoCapability()
    # Boot always validates the registry (extending the UiPart union) before
    # any tool can run; mirror that here so the artifact's ui_parts validate
    # (test_capability_chat_parts_1977.py's pattern).
    registry = CapabilityRegistry()
    registry.register(cap)
    registry.validate(env={})
    ctx_cap = build_capability_context(
        cap,
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None),
        services=RuntimeServices(),
        config={"uppercase": True},
    )
    (source_tool,) = cap.tools(ctx_cap)
    ctx = _node_context({source_tool.name: source_tool})

    result = asyncio.run(ctx.invoke_runtime_tool("tracer_echo", {"text": "hello"}))

    assert isinstance(result, dict)
    assert result["blocks"][0]["text"] == "HELLO"


# ---------------------------------------------------------------------------
# Native tool invocation — return shapes
# ---------------------------------------------------------------------------


def test_native_preserves_bare_tool_invocation_result_tools_unchanged() -> None:
    @lc_tool("bare_tool")
    async def _bare_tool(x: str) -> ToolInvocationResult:
        """A bare-result tool."""
        return ToolInvocationResult(
            tool_ref="probe",
            blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data={"x": x}),),
            sources=(),
        )

    native_tool = _bare_tool
    result = asyncio.run(
        _node_context({native_tool.name: native_tool}).invoke_runtime_tool(
            native_tool.name, {"x": "hello"}
        )
    )

    assert isinstance(result, dict)
    assert result["tool_ref"] == "probe"


def test_native_folds_content_into_blocks_when_artifact_carries_none() -> None:
    @lc_tool("tracer_echo_shaped", response_format="content_and_artifact")
    async def _tracer_echo_shaped(text: str) -> tuple[str, ToolInvocationResult]:
        """Mirrors tracer_echo's exact shape: answer in content, artifact has
        only ui_parts, no blocks."""
        return text.upper(), ToolInvocationResult(tool_ref="tracer_echo_shaped")

    native_tool = _tracer_echo_shaped
    result = asyncio.run(
        _node_context({native_tool.name: native_tool}).invoke_runtime_tool(
            native_tool.name, {"text": "hello"}
        )
    )

    assert isinstance(result, dict)
    assert result["blocks"][0]["text"] == "HELLO"


def test_native_does_not_override_artifact_blocks_already_present() -> None:
    @lc_tool("has_blocks_tool", response_format="content_and_artifact")
    async def _has_blocks_tool(x: str) -> tuple[str, ToolInvocationResult]:
        """An artifact that already carries its own blocks."""
        del x
        return "ignored content", ToolInvocationResult(
            tool_ref="has_blocks_tool",
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text="real payload"),),
        )

    native_tool = _has_blocks_tool
    result = asyncio.run(
        _node_context({native_tool.name: native_tool}).invoke_runtime_tool(
            native_tool.name, {"x": "y"}
        )
    )

    assert isinstance(result, dict)
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["text"] == "real payload"


def test_native_only_unwraps_tuples_declared_content_and_artifact() -> None:
    @lc_tool("plain_pair_tool")
    async def _plain_pair_tool(x: str) -> tuple[bool, str]:
        """Returns an ordinary (success, message) pair — NOT content_and_artifact."""
        return True, f"processed {x}"

    native_tool = _plain_pair_tool
    result = asyncio.run(
        _node_context({native_tool.name: native_tool}).invoke_runtime_tool(
            native_tool.name, {"x": "hello"}
        )
    )

    assert result == [True, "processed hello"]


def test_native_invocation_supports_sync_tool_with_content_and_artifact() -> None:
    @lc_tool("sync_artifact_tool", response_format="content_and_artifact")
    def _sync_artifact_tool(x: str) -> tuple[str, ToolInvocationResult]:
        """A synchronous tool using the native artifact convention."""
        return x, ToolInvocationResult(tool_ref="sync_artifact_tool")

    result = asyncio.run(
        _node_context(
            {_sync_artifact_tool.name: _sync_artifact_tool}
        ).invoke_runtime_tool(_sync_artifact_tool.name, {"x": "hello"})
    )
    assert isinstance(result, dict)
    assert result["blocks"][0]["text"] == "hello"


def test_invoke_runtime_tool_event_reflects_tool_reported_is_error() -> None:
    """
    CAPAB-02: a capability tool reports failure by returning
    `is_error=True` (RFC §3.9 — never raise for an expected failure). The
    `ToolResultRuntimeEvent` `invoke_runtime_tool` emits must reflect that,
    not hardcode `is_error=False` on every non-exception return.
    """

    @lc_tool("failing_probe", response_format="content_and_artifact")
    async def _failing_probe(x: str) -> tuple[str, ToolInvocationResult]:
        """A tool that reports failure via is_error, never raises."""
        del x
        return "boom", ToolInvocationResult(tool_ref="failing_probe", is_error=True)

    native_tool = _failing_probe
    events: list[RuntimeEvent] = []
    ctx = _node_context({native_tool.name: native_tool}, events=events)

    result = asyncio.run(ctx.invoke_runtime_tool("failing_probe", {"x": "y"}))

    assert isinstance(result, dict)
    assert result["is_error"] is True
    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.tool_name == "failing_probe"
    assert event.is_error is True


@pytest.mark.parametrize("failure", ["execution", "validation"])
@pytest.mark.parametrize("response_format", ["content", "content_and_artifact"])
def test_native_handled_error_status_requires_artifact_format(
    failure, response_format
) -> None:
    from langchain_core.tools import ToolException

    @lc_tool("handled_probe", response_format=response_format)
    async def probe(count: int) -> tuple[str, ToolInvocationResult]:
        """A native tool with handled failures."""
        raise ToolException("execution failed")

    probe.handle_tool_error = True
    probe.handle_validation_error = True
    events: list[RuntimeEvent] = []
    context = _node_context({probe.name: probe}, events=events)
    result = asyncio.run(
        context.invoke_runtime_tool(
            probe.name, {"count": "invalid" if failure == "validation" else 1}
        )
    )
    assert isinstance(result, str)
    assert next(
        e for e in events if isinstance(e, ToolResultRuntimeEvent)
    ).is_error == (response_format == "content_and_artifact")


def test_native_tool_validates_and_supplies_defaults_before_execution() -> None:
    @lc_tool("default_probe")
    async def probe(count: int = 7) -> dict:
        """Return the validated value and its type."""
        return {"count": count, "type": type(count).__name__}

    context = _node_context({probe.name: probe})
    assert asyncio.run(context.invoke_runtime_tool(probe.name, {})) == {
        "count": 7,
        "type": "int",
    }
    assert asyncio.run(context.invoke_runtime_tool(probe.name, {"count": "3"})) == {
        "count": 3,
        "type": "int",
    }


@pytest.mark.parametrize("artifact", [{"payload": "kept"}, [1, 2]])
def test_native_tool_preserves_non_fred_artifacts(artifact) -> None:
    @lc_tool("artifact_probe", response_format="content_and_artifact")
    async def probe() -> tuple[str, object]:
        """Return a plain structured artifact."""
        return "summary", artifact

    result = asyncio.run(
        _node_context({probe.name: probe}).invoke_runtime_tool(probe.name, {})
    )
    assert result == artifact


def test_invoke_runtime_tool_populates_latency_ms_on_success_and_error() -> None:
    """
    PR #2067 review (Copilot): `ToolResultRuntimeEvent.latency_ms` exists in
    the SDK contract (react_runtime.py already populates it), but
    `invoke_runtime_tool` never measured elapsed time — every Graph tool
    result had `latency_ms=None`, so the trace UI/persistence couldn't show
    latency for Graph agents at all. Covers both the success and the
    exception path.
    """

    @lc_tool("slow_probe")
    async def _slow_probe(x: str) -> str:
        """A tool that takes a small, measurable amount of time."""
        await asyncio.sleep(0.01)
        return x

    @lc_tool("raising_probe")
    async def _raising_probe(x: str) -> str:
        """A tool that raises instead of returning."""
        del x
        raise RuntimeError("boom")

    events: list[RuntimeEvent] = []
    ctx = _node_context(
        {"slow_probe": _slow_probe, "raising_probe": _raising_probe}, events=events
    )

    asyncio.run(ctx.invoke_runtime_tool("slow_probe", {"x": "y"}))
    (success_event,) = [
        e
        for e in events
        if isinstance(e, ToolResultRuntimeEvent) and e.tool_name == "slow_probe"
    ]
    assert success_event.latency_ms is not None
    assert success_event.latency_ms >= 0

    with pytest.raises(RuntimeError):
        asyncio.run(ctx.invoke_runtime_tool("raising_probe", {"x": "y"}))
    (error_event,) = [
        e
        for e in events
        if isinstance(e, ToolResultRuntimeEvent) and e.tool_name == "raising_probe"
    ]
    assert error_event.latency_ms is not None
    assert error_event.is_error is True


def test_invoke_runtime_tool_reads_sources_and_ui_parts_from_typed_result() -> None:
    """CAPAB-02: the event's `sources`/`ui_parts` must come from the real
    `ToolInvocationResult`, not silently stay empty on the Graph path while
    ReAct's own trace already carries them."""

    hit = VectorSearchHit(
        uid="d1", title="Doc", content="body", score=1.0, type="document"
    )

    @lc_tool("sourced_probe", response_format="content_and_artifact")
    async def _sourced_probe(x: str) -> tuple[str, ToolInvocationResult]:
        """A tool whose artifact carries sources."""
        del x
        return "ok", ToolInvocationResult(tool_ref="sourced_probe", sources=(hit,))

    native_tool = _sourced_probe
    events: list[RuntimeEvent] = []
    ctx = _node_context({native_tool.name: native_tool}, events=events)

    asyncio.run(ctx.invoke_runtime_tool("sourced_probe", {"x": "y"}))

    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.sources[0].uid == "d1"


def test_invoke_runtime_tool_does_not_misread_an_unrelated_dict_is_error_key() -> None:
    """
    CAPAB-02 hardening: `is_error` must be read off a genuine
    `ToolInvocationResult` instance, not off ANY dict that happens to carry
    an `is_error`-named key for an unrelated reason (e.g. an MCP tool's own
    business payload) — that would misclassify a normal answer as this
    platform's error contract.
    """

    @lc_tool("mcp_like_probe")
    async def _mcp_like_probe(x: str) -> dict:
        """A plain (non-capability) tool returning an ordinary dict payload."""
        del x
        return {"is_error": "not-a-bool-business-value", "answer": 42}

    events: list[RuntimeEvent] = []
    ctx = _node_context({"mcp_like_probe": _mcp_like_probe}, events=events)

    result = asyncio.run(ctx.invoke_runtime_tool("mcp_like_probe", {"x": "y"}))

    assert result == {"is_error": "not-a-bool-business-value", "answer": 42}
    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.is_error is False


# ---------------------------------------------------------------------------
# Capability-vs-MCP name collision guard
# (deferred from Phase 2, resolved here).
# ---------------------------------------------------------------------------


def test_capability_tool_colliding_with_mcp_tool_name_raises() -> None:
    source_tool = _sourced_capability_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))

    with pytest.raises(CapabilityAssemblyError, match=source_tool.name):
        _capability_tools(
            block, mcp_tool_names={source_tool.name, "some_other_mcp_tool"}
        )


def test_capability_tools_merge_cleanly_when_no_mcp_name_collision() -> None:
    source_tool = _sourced_capability_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))

    native_tool = _capability_tools(block, mcp_tool_names={"unrelated_tool"})

    assert native_tool == (source_tool,)
    assert native_tool[0] is source_tool


def test_capability_tools_returns_empty_for_no_capability_block() -> None:
    assert _capability_tools(None, mcp_tool_names=set()) == ()


# ---------------------------------------------------------------------------
# GraphRuntime.build_executor — the actual wiring point (Phase 4 scope).
# ---------------------------------------------------------------------------


class _FakeToolProvider(ToolProviderPort):
    """Minimal `ToolProviderPort` stand-in returning a fixed MCP tool set."""

    def __init__(self, tools: tuple[RuntimeToolHandle, ...]) -> None:
        self._tools = tools

    def bind(self, binding: BoundRuntimeContext) -> None:
        del binding

    async def activate(self) -> None:
        return None

    def get_tools(self) -> tuple[RuntimeToolHandle, ...]:
        return self._tools

    async def aclose(self) -> None:
        return None


def _min_graph_agent_definition():
    """The minimal `GraphAgentDefinition` fixture pattern also used by
    `test_agent_app.py::test_build_capability_block_for_graph_agent_returns_tools`."""

    from collections.abc import Mapping as _Mapping

    from fred_sdk.contracts.models import (
        GraphAgentDefinition,
        GraphDefinition,
        GraphNodeDefinition,
    )
    from fred_sdk.graph.runtime import GraphNodeResult
    from pydantic import BaseModel

    class _MinInput(BaseModel):
        message: str = ""

    class _MinState(BaseModel):
        message: str = ""

    class _MinGraphAgent(GraphAgentDefinition):
        agent_id: str = "test.graph_capability_bridge"
        role: str = "test"
        description: str = "test"

        def build_graph(self) -> GraphDefinition:
            return GraphDefinition(
                state_model_name="MinState",
                entry_node="n",
                nodes=(GraphNodeDefinition(node_id="n", title="N"),),
            )

        def input_model(self) -> type[BaseModel]:
            return _MinInput

        def state_model(self) -> type[BaseModel]:
            return _MinState

        def output_model(self) -> type[BaseModel]:
            return _MinInput

        def build_initial_state(
            self, input_model: BaseModel, binding: BoundRuntimeContext
        ) -> BaseModel:
            return _MinState(message=getattr(input_model, "message", ""))

        def node_handlers(self) -> _Mapping[str, object]:
            async def _n(state: BaseModel, ctx: object) -> GraphNodeResult:
                del state, ctx
                return GraphNodeResult()

            return {"n": _n}

        def build_output(self, state: BaseModel) -> BaseModel:
            return _MinInput(message=getattr(state, "message", ""))

    return _MinGraphAgent()


def test_build_executor_merges_mcp_and_capability_tools() -> None:
    from fred_runtime.graph.graph_executor import GraphExecutor
    from fred_runtime.graph.graph_runtime import GraphRuntime

    @lc_tool("mcp_probe")
    def _mcp_probe(text: str) -> str:
        """An MCP-provided tool."""
        return text

    source_tool = _sourced_capability_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))
    runtime = GraphRuntime(
        definition=_min_graph_agent_definition(),
        services=RuntimeServices(tool_provider=_FakeToolProvider((_mcp_probe,))),
        capability_block=block,
    )

    executor = asyncio.run(runtime.build_executor(_binding()))
    assert isinstance(executor, GraphExecutor)

    runtime_tools = executor._runtime_tools  # pyright: ignore[reportPrivateUsage]
    assert set(runtime_tools) == {"mcp_probe", "corpus_search"}
    assert runtime_tools["corpus_search"] is source_tool


def test_build_executor_raises_on_capability_mcp_name_collision() -> None:
    from fred_runtime.graph.graph_runtime import GraphRuntime

    source_tool = _sourced_capability_tool()

    @lc_tool(source_tool.name)
    def _colliding_mcp_tool(question: str) -> str:
        """An MCP tool that happens to share the capability tool's name."""
        return question

    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))
    runtime = GraphRuntime(
        definition=_min_graph_agent_definition(),
        services=RuntimeServices(
            tool_provider=_FakeToolProvider((_colliding_mcp_tool,))
        ),
        capability_block=block,
    )

    with pytest.raises(CapabilityAssemblyError, match=source_tool.name):
        asyncio.run(runtime.build_executor(_binding()))
