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
Wiring guard for the `mermaid` scenario of `test_assistant` (issue #2382).

Why this file exists:
The scenario's value is manual - a developer types `mermaid` in the chat and
checks that the frontend sanitizer repairs deliberately malformed diagrams
instead of showing a parse error. That only works while the keyword still
routes to the step, and while the payload still *is* malformed. Both are easy
to break silently: a stray `elif` reordering kills the route, and a
well-meaning cleanup "fixing" the diagrams turns the fixture into a no-op that
passes forever without testing anything.

The repair logic itself is covered on the frontend side
(`mermaidSanitizer.test.ts`); nothing here re-tests it.

Offline only: no model, no pod, no docker.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_agents.test_assistant.graph_agent import TestAssistantGraphAgent
from fred_agents.test_assistant.graph_state import TestState
from fred_agents.test_assistant.graph_steps import (
    _MERMAID_PAYLOAD,
    dispatch_step,
    mermaid_step,
)
from fred_sdk import GraphNodeContext


class _FakeContext:
    """Minimal double: the two scenario steps only emit and read tuning."""

    def __init__(self) -> None:
        self.tuning_values: dict[str, Any] = {}
        self.statuses: list[tuple[str, str | None]] = []
        self.deltas: list[str] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))

    def emit_assistant_delta(self, delta: str) -> None:
        self.deltas.append(delta)


def _ctx() -> tuple[_FakeContext, GraphNodeContext]:
    fake = _FakeContext()
    return fake, cast(GraphNodeContext, fake)


@pytest.mark.asyncio
async def test_mermaid_keyword_routes_to_the_mermaid_scenario() -> None:
    """`mermaid ...` must reach mermaid_step, not the fallback help menu."""
    _, ctx = _ctx()
    state = TestState(latest_user_text="mermaid please")

    result = await dispatch_step(state, ctx)

    assert result.route_key == "mermaid"
    assert result.state_update["scenario"] == "mermaid"


@pytest.mark.asyncio
async def test_markdown_keyword_still_routes_to_its_own_scenario() -> None:
    """The two `m` keywords must not shadow each other."""
    _, ctx = _ctx()

    result = await dispatch_step(TestState(latest_user_text="markdown"), ctx)

    assert result.route_key == "markdown"


@pytest.mark.asyncio
async def test_mermaid_step_streams_the_payload_and_finalizes() -> None:
    fake, ctx = _ctx()

    result = await mermaid_step(TestState(latest_user_text="mermaid"), ctx)

    assert fake.deltas == [_MERMAID_PAYLOAD]
    assert result.state_update["final_text"] == _MERMAID_PAYLOAD
    assert result.state_update["done_reason"] == "mermaid_complete"


def test_graph_registers_the_mermaid_node_and_its_edge() -> None:
    workflow = TestAssistantGraphAgent.workflow
    assert workflow is not None

    assert workflow.nodes["mermaid"] is mermaid_step
    assert workflow.edges["mermaid"] == "finalize"


def test_payload_is_still_malformed_on_purpose() -> None:
    """
    Guard the fixture: each fence must keep at least one bare multi-word
    endpoint (the #2382 shape), otherwise the scenario silently stops
    exercising the sanitizer.
    """
    fences = [
        block.split("```", 1)[0] for block in _MERMAID_PAYLOAD.split("```mermaid\n")[1:]
    ]
    assert len(fences) == 4, "expected 4 mermaid fences in the fixture"

    # The exact lines reported in #2382: a node declared once, then referenced
    # by its label text on the following lines.
    assert "BackendPython --> LLMAzure[LLM Azure]" in fences[0]
    assert "OpenSearch -->|Recherche semantique| LLM Azure" in fences[0]

    assert "Base de données" in fences[1]
    assert "LLM Azure ---o Vector Store;" in fences[2]
    # Fence 4 is the non-regression case: an arrow inside a bracket label.
    assert "A[Flow (v2): raw data --> clean data]" in fences[3]
