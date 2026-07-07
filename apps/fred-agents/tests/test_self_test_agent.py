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

from types import SimpleNamespace
from typing import cast

import pytest
from fred_agents.registry import build_registry
from fred_agents.self_test.graph_state import SelfTestState
from fred_agents.self_test.graph_steps import retrieve_step
from fred_core.store import VectorSearchHit
from fred_sdk import GraphNodeContext


class _FakeContext:
    """Tiny graph-node context: records the tool call, returns canned hits."""

    def __init__(
        self,
        *,
        sources: list[VectorSearchHit],
        tuning_values=None,
        context_prompt_text: str | None = None,
    ) -> None:
        self._result = SimpleNamespace(sources=tuple(sources), blocks=())
        self.tuning_values = dict(tuning_values or {})
        # Mirror BoundRuntimeContext.runtime_context.context_prompt_text so the
        # agent can echo the conversation-scoped (marketplace) prompt.
        self.binding = SimpleNamespace(
            runtime_context=SimpleNamespace(context_prompt_text=context_prompt_text)
        )
        self.statuses: list[tuple[str, str | None]] = []
        self.tool_calls: list[tuple[str, dict[str, object]]] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))

    async def invoke_tool(self, tool_ref: str, payload: dict[str, object]) -> object:
        self.tool_calls.append((tool_ref, dict(payload)))
        return self._result


def _ctx(ctx: _FakeContext) -> GraphNodeContext:
    return cast(GraphNodeContext, ctx)


@pytest.mark.asyncio
async def test_echoes_retrieved_marker() -> None:
    hit = VectorSearchHit(
        uid="d1",
        title="Alpha",
        content="The festival is in Marchtober.",
        score=0.9,
        type="md",
    )
    ctx = _FakeContext(sources=[hit])

    result = await retrieve_step(
        SelfTestState(latest_user_text="When is the festival?"), _ctx(ctx)
    )

    update = result.state_update
    assert update["hit_count"] == 1
    assert "Marchtober" in str(update["final_text"])
    assert update["done_reason"] == "self_test_ok"
    # It used the real knowledge-search tool with the user's question and default top_k.
    tool_ref, payload = ctx.tool_calls[0]
    assert payload == {"query": "When is the festival?", "top_k": 5}


@pytest.mark.asyncio
async def test_reports_empty_scope() -> None:
    ctx = _FakeContext(sources=[])

    result = await retrieve_step(SelfTestState(latest_user_text="anything"), _ctx(ctx))

    assert result.state_update["hit_count"] == 0
    assert result.state_update["done_reason"] == "self_test_empty"
    assert "no chunks" in str(result.state_update["final_text"]).lower()


@pytest.mark.asyncio
async def test_top_k_is_tunable() -> None:
    hit = VectorSearchHit(uid="d1", title="A", content="x", score=0.5, type="md")
    ctx = _FakeContext(sources=[hit], tuning_values={"settings.top_k": 3})

    await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    assert ctx.tool_calls[0][1]["top_k"] == 3


@pytest.mark.asyncio
async def test_echoes_system_prompt_tuning() -> None:
    """Path A: the per-instance system prompt (tuning) is echoed back."""
    ctx = _FakeContext(
        sources=[],
        tuning_values={"prompts.system": "SYSPROMPT-abc123"},
    )

    result = await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    final_text = str(result.state_update["final_text"])
    assert "system_prompt: SYSPROMPT-abc123" in final_text
    # No conversation prompt was attached this turn.
    assert "context_prompt: (none)" in final_text


@pytest.mark.asyncio
async def test_echoes_context_prompt_text() -> None:
    """Path B: the conversation-scoped (marketplace) prompt is echoed back."""
    ctx = _FakeContext(
        sources=[],
        context_prompt_text="CTXPROMPT-xyz789",
    )

    result = await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    final_text = str(result.state_update["final_text"])
    assert "context_prompt: CTXPROMPT-xyz789" in final_text
    assert "system_prompt: (none)" in final_text


def test_agent_is_registered() -> None:
    assert "fred.github.self_test" in build_registry()
