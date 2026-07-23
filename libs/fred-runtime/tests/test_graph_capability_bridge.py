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
Graph agent <-> `AgentCapability` bridge (NOTES-GRAPH-CAPABILITY-BRIDGE.md
Phase 4).

Why this file exists:
- Phase 1 (`test_capability_tool_return_convention.py`) proved that a
  `content_and_artifact` capability tool's `ToolInvocationResult` artifact is
  silently dropped when the tool is invoked with a plain args dict — exactly
  the shape `GraphRuntime.invoke_runtime_tool` / `_GraphNodeExecutionContext`
  use. Phase 4 closes that gap with `_adapt_capability_tool_for_graph`
  (`graph_runtime.py`).
- The single most important test here proves the fix against the REAL
  `invoke_runtime_tool` code path (`_GraphNodeExecutionContext`, the exact
  class `GraphNodeContext` is at runtime), not a hand-rolled mock of it.
- Also covers the capability-vs-MCP tool name collision Phase 2 explicitly
  deferred to Phase 4 (`_adapted_capability_tools`).
"""

from __future__ import annotations

import asyncio

from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.capabilities import (
    CapabilityAssemblyError,
    build_capability_context,
)
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.capabilities.document_access import DocumentAccessCapability
from fred_runtime.graph.graph_runtime import (
    _adapt_capability_tool_for_graph,
    _adapted_capability_tools,
    _GraphNodeExecutionContext,
)
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
    DocumentSearchPort,
    DocumentSearchResult,
    RuntimeServices,
    RuntimeToolHandle,
    ToolProviderPort,
    ToolResultRuntimeEvent,
)
from langchain_core.tools import tool as lc_tool
import pytest


class _FakeDocumentSearchPort(DocumentSearchPort):
    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids=None,
        document_uids=None,
        search_policy=None,
        attachments_only: bool = False,
    ) -> DocumentSearchResult:
        return DocumentSearchResult(
            hits=(
                VectorSearchHit(
                    uid="d1", title="Doc", content="body", score=1.0, type="document"
                ),
            )
        )


def _document_access_tool():
    """The real `document_access` search tool, `response_format="content_and_artifact"`."""

    cap = DocumentAccessCapability()
    ctx = build_capability_context(
        cap,
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None),
        services=RuntimeServices(document_search=_FakeDocumentSearchPort()),
        config={},
    )
    by_name = {t.name: t for t in cap.tools(ctx)}
    return by_name["search_documents_using_vectorization"]


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
    runtime_tools, *, services: RuntimeServices | None = None
) -> _GraphNodeExecutionContext:
    return _GraphNodeExecutionContext(
        binding=_binding(),
        services=services if services is not None else RuntimeServices(),
        model=None,
        model_resolver=None,
        graph_agent_id="graph-agent",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools=runtime_tools,
        tuning_values={},
    )


# ---------------------------------------------------------------------------
# The empirical proof: sources survive the REAL invoke_runtime_tool path.
# ---------------------------------------------------------------------------


def test_adapted_capability_tool_sources_survive_invoke_runtime_tool() -> None:
    """
    Build `document_access`'s real tool, adapt it with
    `_adapt_capability_tool_for_graph` exactly as `GraphRuntime.build_executor`
    would, register it on a real `_GraphNodeExecutionContext` (the class
    `GraphNodeContext` actually is at runtime), and call
    `invoke_runtime_tool` — its real, unmocked implementation. Without the
    Phase 4 adapter this would return a bare content string with no sources
    (Phase 1's finding); with it, `.sources` survives.
    """

    source_tool = _document_access_tool()
    adapted = _adapt_capability_tool_for_graph(source_tool)
    ctx = _node_context({adapted.name: adapted})

    result = asyncio.run(
        ctx.invoke_runtime_tool(
            "search_documents_using_vectorization", {"question": "what is fred?"}
        )
    )

    # `_normalize_runtime_tool_output` model_dumps the bare ToolInvocationResult
    # (no special-cased handling for it exists) — the dict still carries the
    # full `sources` payload, uid included.
    assert isinstance(result, dict)
    assert result["sources"][0]["uid"] == "d1"
    assert result["is_error"] is False


def test_unadapted_capability_tool_loses_sources_via_invoke_runtime_tool() -> None:
    """
    Control case: registering the RAW (unadapted) capability tool reproduces
    Phase 1's finding through the real `invoke_runtime_tool` path — no
    sources, proving the adapter in the test above is load-bearing, not
    a no-op.
    """

    source_tool = _document_access_tool()
    ctx = _node_context({source_tool.name: source_tool})

    result = asyncio.run(
        ctx.invoke_runtime_tool(
            "search_documents_using_vectorization", {"question": "what is fred?"}
        )
    )

    assert isinstance(result, dict)
    assert "sources" not in result


# ---------------------------------------------------------------------------
# _adapt_capability_tool_for_graph — direct unit coverage
# ---------------------------------------------------------------------------


def test_adapt_preserves_bare_tool_invocation_result_tools_unchanged() -> None:
    """A capability tool that already returns a bare `ToolInvocationResult`
    (no `response_format`) needs no unwrapping — the adapter must pass its
    result through unchanged rather than mis-handling it as a 2-tuple."""

    @lc_tool("bare_tool")
    async def _bare_tool(x: str) -> ToolInvocationResult:
        """A bare-result tool."""
        return ToolInvocationResult(
            tool_ref="probe",
            blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data={"x": x}),),
            sources=(),
        )

    adapted = _adapt_capability_tool_for_graph(_bare_tool)
    result = asyncio.run(adapted.ainvoke({"x": "hello"}))

    assert isinstance(result, ToolInvocationResult)
    assert result.tool_ref == "probe"


def test_adapt_only_unwraps_tuples_declared_content_and_artifact() -> None:
    """
    CAPAB-02 hardening: the 2-tuple unwrap must be gated on the tool's own
    `response_format`, not fire for "any 2-tuple" — a plain tool whose normal
    return value happens to be an unrelated 2-tuple must round-trip through
    the adapter unchanged, not have its second element silently reinterpreted
    as an artifact.
    """

    @lc_tool("plain_pair_tool")
    async def _plain_pair_tool(x: str) -> tuple[bool, str]:
        """Returns an ordinary (success, message) pair — NOT content_and_artifact."""
        return True, f"processed {x}"

    adapted = _adapt_capability_tool_for_graph(_plain_pair_tool)
    result = asyncio.run(adapted.ainvoke({"x": "hello"}))

    assert result == (True, "processed hello")


def test_adapt_refuses_sync_tool_with_content_and_artifact() -> None:
    """
    CAPAB-02 hardening: a sync-only tool (`.func`, no `.coroutine`) with
    `response_format="content_and_artifact"` cannot be adapted (there is no
    coroutine to call) and would silently lose its artifact if passed
    through unchanged — refuse loudly instead of guessing.
    """

    @lc_tool("sync_artifact_tool", response_format="content_and_artifact")
    def _sync_artifact_tool(x: str) -> tuple[str, ToolInvocationResult]:
        """A synchronous content_and_artifact tool — should never exist."""
        return x, ToolInvocationResult(tool_ref="sync_artifact_tool")

    with pytest.raises(CapabilityAssemblyError, match="sync_artifact_tool"):
        _adapt_capability_tool_for_graph(_sync_artifact_tool)


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

    adapted = _adapt_capability_tool_for_graph(_failing_probe)
    ctx = _node_context({adapted.name: adapted})

    result = asyncio.run(ctx.invoke_runtime_tool("failing_probe", {"x": "y"}))

    assert isinstance(result, dict)
    assert result["is_error"] is True
    (event,) = [e for e in ctx.events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.tool_name == "failing_probe"
    assert event.is_error is True


def test_invoke_runtime_tool_marks_kpi_status_error_for_reported_failure() -> None:
    """
    CAPAB-02: the span status was fixed to reflect `is_error` (prior round),
    but the KPI timer's `status` dim was not — `_graph_phase_timer` defaults
    it to "ok" whenever no exception propagates (`InMemoryMetricsProvider`'s
    `setdefault("status", "ok")`), so a capability tool reporting failure via
    `ToolInvocationResult(is_error=True)` (never raising, per RFC §3.9) was
    recorded as a successful call. Mirrors the canonical `invoke_tool`
    pattern (`kpi_dims["status"] = "error"`).
    """

    from fred_core.portable import InMemoryMetricsProvider

    @lc_tool("kpi_failing_probe", response_format="content_and_artifact")
    async def _kpi_failing_probe(x: str) -> tuple[str, ToolInvocationResult]:
        """A tool that reports failure via is_error, never raises."""
        del x
        return "boom", ToolInvocationResult(tool_ref="kpi_failing_probe", is_error=True)

    metrics = InMemoryMetricsProvider()
    adapted = _adapt_capability_tool_for_graph(_kpi_failing_probe)
    ctx = _node_context(
        {adapted.name: adapted}, services=RuntimeServices(metrics=metrics)
    )

    asyncio.run(ctx.invoke_runtime_tool("kpi_failing_probe", {"x": "y"}))

    assert len(metrics.timers) == 1
    assert metrics.timers[0].dims["status"] == "error"


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

    adapted = _adapt_capability_tool_for_graph(_sourced_probe)
    ctx = _node_context({adapted.name: adapted})

    asyncio.run(ctx.invoke_runtime_tool("sourced_probe", {"x": "y"}))

    (event,) = [e for e in ctx.events if isinstance(e, ToolResultRuntimeEvent)]
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

    ctx = _node_context({"mcp_like_probe": _mcp_like_probe})

    result = asyncio.run(ctx.invoke_runtime_tool("mcp_like_probe", {"x": "y"}))

    assert result == {"is_error": "not-a-bool-business-value", "answer": 42}
    (event,) = [e for e in ctx.events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.is_error is False


# ---------------------------------------------------------------------------
# _adapted_capability_tools — the capability-vs-MCP name collision guard
# (deferred from Phase 2, resolved here).
# ---------------------------------------------------------------------------


def test_capability_tool_colliding_with_mcp_tool_name_raises() -> None:
    source_tool = _document_access_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))

    with pytest.raises(CapabilityAssemblyError, match=source_tool.name):
        _adapted_capability_tools(
            block, mcp_tool_names={source_tool.name, "some_other_mcp_tool"}
        )


def test_capability_tools_merge_cleanly_when_no_mcp_name_collision() -> None:
    source_tool = _document_access_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))

    adapted = _adapted_capability_tools(block, mcp_tool_names={"unrelated_tool"})

    assert [t.name for t in adapted] == [source_tool.name]


def test_adapted_capability_tools_returns_empty_for_no_capability_block() -> None:
    assert _adapted_capability_tools(None, mcp_tool_names=set()) == ()


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


def test_build_executor_merges_mcp_and_adapted_capability_tools() -> None:
    from fred_runtime.graph.graph_runtime import (
        GraphRuntime,
        _DeterministicGraphExecutor,
    )

    @lc_tool("mcp_probe")
    def _mcp_probe(text: str) -> str:
        """An MCP-provided tool."""
        return text

    source_tool = _document_access_tool()
    block = CapabilityAgentBlock(middleware=(), hitl={}, tools=(source_tool,))
    runtime = GraphRuntime(
        definition=_min_graph_agent_definition(),
        services=RuntimeServices(tool_provider=_FakeToolProvider((_mcp_probe,))),
        capability_block=block,
    )

    executor = asyncio.run(runtime.build_executor(_binding()))
    assert isinstance(executor, _DeterministicGraphExecutor)

    runtime_tools = executor._runtime_tools  # pyright: ignore[reportPrivateUsage]
    assert set(runtime_tools) == {"mcp_probe", "search_documents_using_vectorization"}
    # The capability tool object registered on the executor is the adapted
    # wrapper, not the raw ReAct-shaped one — proven by response_format
    # falling back to LangChain's "content" default (the raw tool is
    # "content_and_artifact").
    adapted_in_executor = runtime_tools["search_documents_using_vectorization"]
    assert adapted_in_executor.response_format == "content"


def test_build_executor_raises_on_capability_mcp_name_collision() -> None:
    from fred_runtime.graph.graph_runtime import GraphRuntime

    source_tool = _document_access_tool()

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
