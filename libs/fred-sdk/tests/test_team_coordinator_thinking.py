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
Offline unit tests for TeamAgent coordinator routing observability.

Coverage:
- route mode coordinator (`_make_route_coordinator_step`) opens a "planning"
  thought, writes the model's stated reasoning, and concludes with the chosen
  member — instead of only returning a silent `route_key`
- dynamic mode coordinator (`_make_coordinator_step`) does the same, including
  the "done" terminal case

Why this exists:
- before this change, `_CoordinatorDecision.reasoning` was computed by the
  model but discarded; the routing decision was invisible to the chat UI and
  samples worked around it with ad-hoc text markers baked into system prompts
- this locks in the fix: any TeamAgent gets a visible routing trace for free

Ref: docs/swift/rfc/AGENT-THINKING-API-RFC.md Amendment C.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import Any, cast

from fred_sdk.graph import GraphNodeContext, GraphNodeResult
from fred_sdk.graph.authoring.api import GraphStepHandler
from fred_sdk.graph.authoring.team_api import (
    AgentSpec,
    TeamState,
    _CoordinatorDecision,
    _make_coordinator_step,
    _make_route_coordinator_step,
)


def _run_step(
    step: GraphStepHandler, state: TeamState, context: _CoordinatorContext
) -> GraphNodeResult:
    """Run a `@typed_node`-decorated coordinator step and await its result.

    `GraphStepHandler` is typed as sync-or-async (it also wraps plain
    functions), but every step built by `team_api.py` is `async def` — this
    narrows that for the type checker in one place instead of at every call.
    """
    coro = cast(
        "Coroutine[Any, Any, GraphNodeResult]",
        step(state, cast(GraphNodeContext, context)),
    )
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _FakeThought:
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    async def write(self, text: str) -> None:
        self._sink.append(f"write:{text}")

    async def conclude(self, text: str) -> None:
        self._sink.append(f"conclude:{text}")


class _CoordinatorContext:
    """
    Fake graph context scripting one structured-model decision and recording
    every `thinking()` call, so the coordinator's routing rationale can be
    asserted without a real model or runtime.
    """

    def __init__(self, decision: _CoordinatorDecision) -> None:
        self._decision = decision
        self.thinking_calls: list[tuple[str, str | None]] = []
        self.thought_events: list[str] = []

    @property
    def model(self) -> object:
        # `structured_model_step` only checks this for `is None`; any truthy
        # sentinel keeps it on the `invoke_structured_model` path below.
        return object()

    async def invoke_structured_model(
        self, output_model, messages, *, operation="default"
    ):  # type: ignore[no-untyped-def]
        return self._decision

    @asynccontextmanager
    async def thinking(self, phase: str, *, title: str | None = None):  # type: ignore[no-untyped-def]
        self.thinking_calls.append((phase, title))
        yield _FakeThought(self.thought_events)


def _state(message: str = "Convert 2.5 km to meters.") -> TeamState:
    return TeamState(user_message=message)


_MEMBERS = (
    AgentSpec(name="Math Specialist", role="Arithmetic", agent_ref="a.math"),
    AgentSpec(name="Writing Specialist", role="Prose", agent_ref="a.writer"),
)


# ---------------------------------------------------------------------------
# route mode
# ---------------------------------------------------------------------------


def test_route_coordinator_opens_a_planning_thought() -> None:
    """
    Verify the route-mode coordinator wraps its decision in `thinking("planning", ...)`.

    Why: silent routing left testers with no way to see why a member was chosen.
    How: run the coordinator step against a fake context and inspect the
         recorded `thinking()` call.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(
            next_member="Math Specialist", reasoning="Arithmetic request."
        )
    )
    step = _make_route_coordinator_step(_MEMBERS, "Pick one.")

    _run_step(step, _state(), context)

    assert context.thinking_calls == [("planning", "Choosing a specialist")]


def test_route_coordinator_writes_reasoning_and_concludes_with_target() -> None:
    """
    Verify the thought body carries the model's reasoning and the final target.

    Why: the thought must be useful, not just present.
    How: assert both the written reasoning text and the concluding member name.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(
            next_member="Math Specialist", reasoning="Arithmetic request."
        )
    )
    step = _make_route_coordinator_step(_MEMBERS, "Pick one.")

    _run_step(step, _state(), context)

    assert context.thought_events == [
        "write:Arithmetic request.",
        "conclude:Routing to Math Specialist.",
    ]


def test_route_coordinator_still_returns_correct_route_key() -> None:
    """
    Verify the thinking wrapper doesn't change the existing routing contract.

    Why: `route_key` drives the actual graph edge; a regression here would
         silently break every route-mode TeamAgent.
    How: assert the returned `StepResult.route_key` matches the chosen node id.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(
            next_member="Writing Specialist", reasoning="Rewrite request."
        )
    )
    step = _make_route_coordinator_step(_MEMBERS, "Pick one.")

    result = _run_step(step, _state(), context)

    assert result.route_key == "writing_specialist"


def test_route_coordinator_clamps_unknown_member_in_thought_and_route() -> None:
    """
    Verify an unknown model-chosen member falls back to the first declared one.

    Why: the guard clause existed before this change; it must still apply to
         both the returned route and the thought conclusion.
    How: script a decision naming a member outside `_MEMBERS` and check both.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(next_member="Unknown Specialist", reasoning="Bad output.")
    )
    step = _make_route_coordinator_step(_MEMBERS, "Pick one.")

    result = _run_step(step, _state(), context)

    assert result.route_key == "math_specialist"
    assert context.thought_events[-1] == "conclude:Routing to Math Specialist."


# ---------------------------------------------------------------------------
# dynamic mode
# ---------------------------------------------------------------------------


def test_dynamic_coordinator_opens_a_planning_thought() -> None:
    """
    Verify the dynamic-mode coordinator also wraps its decision in a thought.

    Why: dynamic mode had the same silent-`reasoning` bug as route mode.
    How: run the coordinator step and inspect the recorded `thinking()` call.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(
            next_member="Math Specialist", reasoning="Start with math."
        )
    )
    step = _make_coordinator_step(_MEMBERS, "Coordinate.")

    _run_step(step, _state(), context)

    assert context.thinking_calls == [("planning", "Choosing the next specialist")]


def test_dynamic_coordinator_concludes_task_complete_on_done() -> None:
    """
    Verify the "done" terminal case gets a distinct, readable conclusion.

    Why: `done` is a special route key, not a member name — the thought text
         must reflect that instead of saying "Next: done."
    How: script a `next_member="done"` decision and check the conclusion text.
    """
    context = _CoordinatorContext(
        _CoordinatorDecision(next_member="done", reasoning="All specialists have run.")
    )
    step = _make_coordinator_step(_MEMBERS, "Coordinate.")

    result = _run_step(step, _state(), context)

    assert result.route_key == "done"
    assert context.thought_events == [
        "write:All specialists have run.",
        "conclude:Task complete.",
    ]
