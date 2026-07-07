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
Tests for the in-process kf_vector_search toolkit (MIGR-03.03).

The point of the toolkit is that the search tool returns typed `VectorSearchHit`
sources on a `ToolInvocationResult` artifact — that artifact is what makes the chat
Sources panel render (kea parity). These tests lock that contract without any HTTP.
"""

from __future__ import annotations

import fred_runtime.integrations.kf_vector_search.toolkit as toolkit_mod
import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.integrations.inprocess_toolkit_registry import build_inprocess_toolkit
from fred_runtime.integrations.kf_vector_search import (
    KF_VECTOR_SEARCH_PROVIDER,
    KfVectorSearchToolkit,
)
from fred_runtime.react.react_tool_rendering import render_tool_result
from fred_sdk.contracts.context import RuntimeContext, ToolInvocationResult
from fred_sdk.contracts.models import AgentTuning


class _FakeSettings:
    """Matches the AgentSettingsLike protocol (id / team_id / tuning)."""

    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None


class _FakeAgent:
    """Minimal shim matching what VectorSearchClient + the toolkit read."""

    def __init__(self, runtime_context: RuntimeContext) -> None:
        self.runtime_context = runtime_context
        self.agent_settings: AgentSettingsLike = _FakeSettings()

    def refresh_user_access_token(self) -> str:
        return "token"


class _FakeSearchClient:
    """Stand-in for VectorSearchClient — records the call, returns preset hits."""

    last_kwargs: dict[str, object] = {}

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def search(self, **kwargs: object) -> list[VectorSearchHit]:
        _FakeSearchClient.last_kwargs = kwargs
        return [
            VectorSearchHit(
                uid="d1", title="Doc 1", content="alpha", score=0.9, type="document"
            ),
            VectorSearchHit(
                uid="d2", title="Doc 2", content="beta", score=0.7, type="document"
            ),
        ]


def _build_search_tool(
    monkeypatch: pytest.MonkeyPatch, runtime_context: RuntimeContext
):
    monkeypatch.setattr(toolkit_mod, "VectorSearchClient", _FakeSearchClient)
    toolkit = KfVectorSearchToolkit(agent=_FakeAgent(runtime_context))
    tools = toolkit.tools()
    assert len(tools) == 1
    return tools[0]


@pytest.mark.asyncio
async def test_search_returns_tool_invocation_result_with_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = RuntimeContext(session_id="s-1", team_id="team-1")
    tool = _build_search_tool(monkeypatch, ctx)

    # The runtime-provider resolver invokes provider tools with a plain args dict
    # (NOT a tool_call), so the tool must return a ToolInvocationResult directly for
    # its sources to survive — this is the exact contract that drives the panel.
    result = await tool.ainvoke({"question": "what is alpha?"})

    assert isinstance(result, ToolInvocationResult)
    assert result.tool_ref == KF_VECTOR_SEARCH_PROVIDER
    # The panel-driving contract: typed hits are carried on the result.
    assert [h.uid for h in result.sources] == ["d1", "d2"]
    # The LLM-facing content is the JSON hit list, carried in blocks.
    assert "alpha" in render_tool_result(result)


@pytest.mark.asyncio
async def test_general_only_scope_short_circuits_without_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = RuntimeContext(
        session_id="s-1", team_id="team-1", search_rag_scope="general_only"
    )
    tool = _build_search_tool(monkeypatch, ctx)
    _FakeSearchClient.last_kwargs = {}

    result = await tool.ainvoke({"question": "irrelevant"})

    assert isinstance(result, ToolInvocationResult)
    assert result.sources == ()
    # No retrieval was attempted in general-only mode.
    assert _FakeSearchClient.last_kwargs == {}


def test_registry_builds_toolkit_for_known_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(toolkit_mod, "VectorSearchClient", _FakeSearchClient)
    ctx = RuntimeContext(session_id="s-1", team_id="team-1")
    toolkit = build_inprocess_toolkit(KF_VECTOR_SEARCH_PROVIDER, _FakeAgent(ctx))
    assert isinstance(toolkit, KfVectorSearchToolkit)


def test_registry_returns_none_for_unknown_provider() -> None:
    ctx = RuntimeContext(session_id="s-1", team_id="team-1")
    assert build_inprocess_toolkit("does-not-exist", _FakeAgent(ctx)) is None
