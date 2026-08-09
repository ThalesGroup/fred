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

from typing import cast

import pytest
from fred_agents.routing_probe.graph_agent import (
    ROUTING_PROBE_ALPHA_AGENT,
    ROUTING_PROBE_BETA_AGENT,
)
from fred_agents.routing_probe.graph_state import PhaseRecord, RoutingProbeState
from fred_agents.routing_probe.graph_steps import finalize_step, routing_step
from fred_sdk import GraphNodeContext
from langchain_core.messages import AIMessage


class _FakeContext:
    """Minimal fake — only what `routing_step` touches."""

    def __init__(
        self,
        *,
        model: object | None = None,
        response: AIMessage | None = None,
    ) -> None:
        self.model = model
        self._response = response
        self.invoke_model_calls: list[tuple[str, ...]] = []
        self.statuses: list[tuple[str, str | None]] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))

    async def invoke_model(self, messages, *, operation: str = "default"):
        self.invoke_model_calls.append((operation,))
        assert self._response is not None, "test forgot to configure a response"
        return self._response


@pytest.mark.asyncio
async def test_routing_step_records_resolved_model_name() -> None:
    """
    Verify a phase step reads the model name straight off response_metadata
    and passes its own operation label through to invoke_model — this is the
    exact signal a team-routing-policy override targets.
    """
    state = RoutingProbeState(latest_user_text="hello")
    context = _FakeContext(
        model=object(),
        response=AIMessage(
            content="Confirmed: routing phase.",
            response_metadata={"model_name": "mistral-small"},
        ),
    )

    result = await routing_step(state, cast(GraphNodeContext, context))

    records = cast(list[PhaseRecord], result.state_update["phase_records"])
    assert len(records) == 1
    assert records[0].phase == "Routing"
    assert records[0].operation == "routing"
    assert records[0].model_name == "mistral-small"
    assert context.invoke_model_calls == [("routing",)]


@pytest.mark.asyncio
async def test_routing_step_degrades_gracefully_without_a_model() -> None:
    """
    Verify the probe stays runnable on a pod with no chat model configured,
    matching the existing test_assistant model_probe convention.
    """
    state = RoutingProbeState(latest_user_text="hello")
    context = _FakeContext(model=None)

    result = await routing_step(state, cast(GraphNodeContext, context))

    records = cast(list[PhaseRecord], result.state_update["phase_records"])
    assert len(records) == 1
    assert "no model configured" in records[0].model_name.lower()
    assert context.invoke_model_calls == []


@pytest.mark.asyncio
async def test_finalize_step_table_covers_every_recorded_phase() -> None:
    """Verify the summary table names every phase, operation, and resolved model."""
    state = RoutingProbeState(
        latest_user_text="hello",
        phase_records=[
            PhaseRecord(
                phase="Routing", operation="routing", model_name="model-a", reply="ok"
            ),
            PhaseRecord(
                phase="Planning",
                operation="planning",
                model_name="model-b",
                reply="ok",
            ),
        ],
    )

    result = await finalize_step(state, cast(GraphNodeContext, _FakeContext()))

    text = cast(str, result.state_update["final_text"])
    assert "routing" in text
    assert "planning" in text
    assert "model-a" in text
    assert "model-b" in text


def test_alpha_and_beta_probes_have_distinct_agent_ids() -> None:
    """
    Verify the two enrolled probe identities are distinct `agent_id`s, not
    just distinct instances — the team-routing agent selector dedupes by
    `source_agent_id`, so an agent-scoped override needs two classes to
    actually distinguish (#2267).
    """
    assert ROUTING_PROBE_ALPHA_AGENT.agent_id != ROUTING_PROBE_BETA_AGENT.agent_id
    assert ROUTING_PROBE_ALPHA_AGENT.agent_id.startswith("fred.github.routing_probe")
    assert ROUTING_PROBE_BETA_AGENT.agent_id.startswith("fred.github.routing_probe")
