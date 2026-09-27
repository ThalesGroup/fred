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
Context-injection tests for `ContextAwareTool`.

KPI timing (`agent.tool_latency_ms`) and the
`agent.tool.invocation.{started,completed}` audit events used to be tested
here directly; that behavior moved to the platform-wide
`ToolObservabilityMiddleware` (#2011) — see
`tests/test_tool_observability_middleware.py` for the equivalent coverage,
now exercised through `awrap_tool_call` for every tool call (MCP-catalog AND
capability-native), not just `ContextAwareTool`-wrapped ones.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import pytest
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_sdk.contracts.context import RuntimeContext, ToolContentKind
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from langchain_core.tools import ArgsSchema, BaseTool
from pydantic import BaseModel


class _SearchArgs(BaseModel):
    question: str
    document_library_tags_ids: list[str] | None = None
    document_uids: list[str] | None = None
    session_id: str | None = None
    owner_filter: str | None = None
    team_id: str | None = None
    include_session_scope: bool | None = None
    include_corpus_scope: bool | None = None


class _FakeSearchTool(BaseTool):
    name: str = "fake.search"
    description: str = "Search tool used to validate context injection."
    args_schema: ArgsSchema | None = _SearchArgs

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "ok"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return "ok"


class _ReadQueryArgs(BaseModel):
    sql: str


class _FailingReadQueryTool(BaseTool):
    name: str = "read_query"
    description: str = "Run a read-only query."
    args_schema: ArgsSchema | None = _ReadQueryArgs
    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"
    failure_message: str = (
        "Error calling read_query. Status code: 400. Response: "
        '{"detail":"Binder Error: Referenced column amount_typo not found"}'
    )

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError(self.failure_message)


class _FakeAgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


@pytest.mark.asyncio
async def test_fastapi_mcp_read_query_400_returns_a_typed_sql_failure() -> None:
    """The model keeps a useful tool result while the runtime gets a trusted,
    HTTP-free SQL failure payload for the trace and observability layers."""
    wrapper = ContextAwareTool(
        base_tool=_FailingReadQueryTool(),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )

    content, artifact = await wrapper._arun(sql="SELECT amount_typo FROM d_sales")

    assert content == "Error: Binder Error: Referenced column amount_typo not found"
    assert "HTTP" not in content
    assert artifact is not None
    assert artifact.is_error is True
    assert len(artifact.blocks) == 1
    assert artifact.blocks[0].kind == ToolContentKind.TEXT
    assert artifact.blocks[0].text == (
        "Binder Error: Referenced column amount_typo not found"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_message",
    [
        (
            "Error calling read_query. Status code: 500. Response: "
            '{"detail":"internal provider secret"}'
        ),
        "Error calling read_query. Status code: 400. Response: not-json",
    ],
)
async def test_read_query_untrusted_failures_keep_only_the_generic_artifact(
    failure_message: str,
) -> None:
    wrapper = ContextAwareTool(
        base_tool=_FailingReadQueryTool(failure_message=failure_message),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )

    _content, artifact = await wrapper._arun(sql="SELECT secret FROM d_sales")

    assert artifact is not None
    assert artifact.is_error is True
    assert artifact.blocks == ()


def test_context_aware_tool_injects_document_filters_for_mcp_search_tools() -> None:
    runtime_context = RuntimeContext(
        session_id="session-1",
        selected_document_libraries_ids=["lib-1"],
        selected_document_uids=["doc-1"],
        search_rag_scope="corpus_only",
    )

    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed({"question": "hello"})

    assert injected["document_library_tags_ids"] == ["lib-1"]
    assert injected["document_uids"] == ["doc-1"]
    assert injected["session_id"] == "session-1"
    assert injected["team_id"] == "team-1"
    assert injected["owner_filter"] == "team"
    assert injected["include_session_scope"] is False
    assert injected["include_corpus_scope"] is True


def test_context_aware_tool_respects_agent_scoped_document_uids() -> None:
    """An explicit per-call document scope is honoured, never overwritten — and it
    suppresses the (widening) picker library filter so the search stays document-
    scoped. This is what lets a deterministic agent compare one document at a time."""
    runtime_context = RuntimeContext(
        selected_document_libraries_ids=["lib-1"],
        selected_document_uids=["doc-1", "doc-2"],
    )
    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed(
        {"question": "hello", "document_uids": ["doc-1"]}
    )

    # explicit scope respected, not replaced by the picker's [doc-1, doc-2]
    assert injected["document_uids"] == ["doc-1"]
    # the picker library filter is NOT injected on top of a document scope
    assert "document_library_tags_ids" not in injected


def test_context_aware_tool_respects_agent_scoped_library() -> None:
    """An explicit per-call library scope is honoured, not replaced by the picker."""
    runtime_context = RuntimeContext(
        selected_document_libraries_ids=["lib-picker"],
        selected_document_uids=["doc-1"],
    )
    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed(
        {"question": "hello", "document_library_tags_ids": ["lib-agent"]}
    )

    assert injected["document_library_tags_ids"] == ["lib-agent"]
