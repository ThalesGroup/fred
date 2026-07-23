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
Return-shape investigation for `AgentCapability.tools()` (Phase 1,
NOTES-GRAPH-CAPABILITY-BRIDGE.md).

Why this file exists:
- the bridge plan assumed a capability tool's `content_and_artifact` tuple
  would "collapse" to a content string when invoked with a plain args dict —
  the shape both `react_tool_resolution._resolve_runtime_provider_tool` and
  `graph_runtime.GraphRuntime.invoke_runtime_tool` use (`tool.ainvoke(dict)`,
  no `ToolCall`). This file proves empirically what actually happens for
  BOTH real invocation shapes, for both candidate return conventions, so the
  Phase 1 decision (keep `document_access`'s tool on
  `response_format="content_and_artifact"`, unchanged) rests on evidence, not
  assumption.

What it proves:
1. `document_access`'s real tool, plain-dict `.ainvoke()` (the Graph /
   runtime-provider-resolver shape): the artifact is not merely collapsed to
   a tuple — it is dropped entirely, and the return is a bare content string.
   Worse than what the original plan assumed, but the conclusion is the same:
   this path cannot recover the artifact from a `content_and_artifact` tool.
2. `document_access`'s real tool, `ToolCall`-dict `.ainvoke()` (the shape
   `create_agent()`'s real ReAct tool-calling loop uses — the ONLY path this
   tool goes through today, Phase 1 included): the artifact survives intact
   on `ToolMessage.artifact`, with `.sources` populated.
3. The candidate fix from the original plan text (switch to a bare
   `ToolInvocationResult` return, `KfVectorSearchToolkit`'s convention) does
   fix path (1) but breaks path (2): a bare pydantic return gets stringified
   into `ToolMessage.content` and `.artifact` is never populated. There is no
   single return convention that is correct on both invocation paths with a
   plain LangChain `@tool` — an adapter at the consumption seam is required
   once Phase 4 actually wires capability tools into Graph's `runtime_tools`.

Conclusion Phase 1 draws from this: since Phase 1 does not wire
`document_access`'s tool into any plain-dict invocation path (only Phase 4
does), keep `response_format="content_and_artifact"` as-is — it is already
correct for the only path this tool is exercised through today.
"""

from __future__ import annotations

import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.capabilities import build_capability_context
from fred_runtime.capabilities.document_access import DocumentAccessCapability
from fred_sdk.contracts.capability import CapabilityIdentity
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    DocumentSearchPort,
    DocumentSearchResult,
    RuntimeServices,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


class _FakePort(DocumentSearchPort):
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
    cap = DocumentAccessCapability()
    ctx = build_capability_context(
        cap,
        identity=_identity(),
        services=RuntimeServices(document_search=_FakePort()),
        config={},
    )
    tools = cap.tools(ctx)
    by_name = {t.name: t for t in tools}
    return by_name["search_documents_using_vectorization"]


# ---------------------------------------------------------------------------
# 1. content_and_artifact + plain-dict `.ainvoke()` (Graph / MCP-provider shape)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_and_artifact_tool_loses_artifact_on_plain_dict_invoke() -> None:
    """
    `invoke_runtime_tool` (graph_runtime.py) and `_resolve_runtime_provider_tool`
    (react_tool_resolution.py) both call `tool.ainvoke(<plain args dict>)` — no
    `ToolCall`. Proves this DROPS the artifact entirely for a
    `content_and_artifact`-format tool: the return is a bare content string,
    not even the 2-tuple `_normalize_runtime_tool_output` in graph_runtime.py
    knows how to unpack.
    """

    the_tool = _document_access_tool()
    result = await the_tool.ainvoke({"question": "what is fred?"})

    assert isinstance(result, str)
    assert "fred" in result or "d1" in result  # plain content only, no artifact


# ---------------------------------------------------------------------------
# 2. content_and_artifact + ToolCall-dict `.ainvoke()` (create_agent()'s real
#    ReAct tool-calling loop — the only path this tool goes through today)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_and_artifact_tool_preserves_artifact_via_tool_call() -> None:
    """
    `create_agent()`'s real ToolNode/message-based execution invokes tools
    with a `ToolCall` dict (id/name/args/type), not a plain dict. Proves the
    artifact — and its `.sources` — survives intact on `ToolMessage.artifact`,
    confirming today's (and Phase 1's) only real consumption path is
    unaffected by keeping `content_and_artifact`.
    """

    the_tool = _document_access_tool()
    message = await the_tool.ainvoke(
        {
            "type": "tool_call",
            "name": the_tool.name,
            "args": {"question": "what is fred?"},
            "id": "call-1",
        }
    )

    assert isinstance(message, ToolMessage)
    assert isinstance(message.artifact, ToolInvocationResult)
    assert [hit.uid for hit in message.artifact.sources] == ["d1"]


# ---------------------------------------------------------------------------
# 3. The naive "fix": bare ToolInvocationResult return (KfVectorSearchToolkit's
#    convention) — fixes path 1, breaks path 2. No single-tool free lunch.
# ---------------------------------------------------------------------------


@tool("bare_result_tool")
async def _bare_result_tool(x: str) -> ToolInvocationResult:
    """A tool returning `ToolInvocationResult` bare, no response_format."""

    return ToolInvocationResult(
        tool_ref="probe",
        blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data={"x": x}),),
        sources=(),
    )


@pytest.mark.asyncio
async def test_bare_result_tool_survives_plain_dict_invoke() -> None:
    """The plain-dict path DOES preserve a bare `ToolInvocationResult` return —
    this is why `KfVectorSearchToolkit` uses this convention for MCP-provider
    tools, which are only ever invoked this way."""

    result = await _bare_result_tool.ainvoke({"x": "hello"})
    assert isinstance(result, ToolInvocationResult)
    assert result.tool_ref == "probe"


@pytest.mark.asyncio
async def test_bare_result_tool_loses_artifact_via_tool_call() -> None:
    """But the SAME bare-return convention, invoked through create_agent()'s
    real ToolCall loop, stringifies the whole result into `ToolMessage.content`
    and never populates `.artifact` — proving a naive migration of
    `document_access` to `KfVectorSearchToolkit`'s convention would silently
    break the ReAct Sources panel it serves today. An adapter at the
    tool-carrier/assembly seam (not a tool return-shape change) is required
    once Phase 4 wires capability tools into Graph's plain-dict invocation."""

    message = await _bare_result_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "bare_result_tool",
            "args": {"x": "hello"},
            "id": "call-1",
        }
    )
    assert isinstance(message, ToolMessage)
    assert message.artifact is None
