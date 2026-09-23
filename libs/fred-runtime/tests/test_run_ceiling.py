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
Every run has a ceiling, and children are bounded.

The ceiling is a wall-clock budget for the whole run — not a per-call timeout,
which bounds one outbound call and is left exactly as configured.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, cast

import pytest
from fred_runtime.app.agent_app import LocalRegistryAgentInvoker
from fred_runtime.app.config import PodExecutionConfig
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    ChildLimitReachedError,
    RunCeilingReachedError,
    RunStopError,
)
from fred_runtime.runtime_support.run_budget import (
    _STOP_MESSAGES,
    DEFAULT_MAX_CONCURRENT_CHILDREN,
    DEFAULT_RUN_CEILING_SECONDS,
    RunLimits,
    RunScope,
    configure_run_limits,
    register_run_child,
    resolve_run_limits,
    set_agent_run_limits_resolver,
    terminal_stop_event,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeErrorEvent,
    RuntimeEvent,
    RuntimeServices,
    RuntimeStopReason,
)
from fred_sdk.graph.runtime import GraphNodeResult
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from test_run_stop_authority import binding, terminal_event


@pytest.fixture(autouse=True)
def restore_run_limits() -> Iterator[None]:
    """Run limits are process-wide deployment configuration; no test may leave
    its own behind."""

    yield
    configure_run_limits()
    set_agent_run_limits_resolver(None)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_the_default_ceiling_is_fifteen_minutes() -> None:
    assert DEFAULT_RUN_CEILING_SECONDS == 900.0
    assert PodExecutionConfig().run_ceiling_seconds == 900.0
    assert (
        PodExecutionConfig().max_concurrent_children == DEFAULT_MAX_CONCURRENT_CHILDREN
    )


def test_deployment_configuration_replaces_the_defaults() -> None:
    configure_run_limits(wall_clock_seconds=120.0, max_concurrent_children=3)

    limits = resolve_run_limits("any-agent")
    assert limits.wall_clock_seconds == 120.0
    assert limits.max_concurrent_children == 3


def test_a_per_agent_override_wins_over_the_deployment_default() -> None:
    configure_run_limits(wall_clock_seconds=120.0)
    set_agent_run_limits_resolver(
        lambda agent_id: (
            RunLimits(wall_clock_seconds=10.0) if agent_id == "slow-agent" else None
        )
    )

    assert resolve_run_limits("slow-agent").wall_clock_seconds == 10.0
    assert resolve_run_limits("other-agent").wall_clock_seconds == 120.0


@pytest.mark.asyncio
async def test_a_per_call_timeout_is_not_reported_as_the_run_ceiling() -> None:
    """
    A run budget and a call budget answer different questions. A timeout that
    comes out of a step while the run still has budget belongs to the call, and
    reporting it as `run_ceiling_reached` would hide a slow receiver behind the
    wrong reason — and end a run that had minutes left.
    """

    scope = RunScope(RunLimits(wall_clock_seconds=30.0))

    class _StepThatTimesOutOnItsOwnCall:
        def __aiter__(self) -> "_StepThatTimesOutOnItsOwnCall":
            return self

        async def __anext__(self) -> object:
            # What a per-call timeout raises from inside the step.
            await asyncio.wait_for(asyncio.sleep(5), timeout=0.01)
            raise AssertionError("unreachable")

    with pytest.raises(TimeoutError):
        await scope.next_event(_StepThatTimesOutOnItsOwnCall())

    # And the run itself is untouched: it still has its budget.
    assert scope.remaining_seconds() > 0


@pytest.mark.asyncio
async def test_the_run_budget_is_what_ends_a_step_that_outlives_it() -> None:
    """The other half of the pair above: when it is the run's own budget that
    runs out, the cancellation lands inside the step and the run — not the
    call — is what ends."""

    scope = RunScope(RunLimits(wall_clock_seconds=0.05))
    cancelled = False

    class _StepLongerThanTheRun:
        def __aiter__(self) -> "_StepLongerThanTheRun":
            return self

        async def __anext__(self) -> object:
            nonlocal cancelled
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled = True
                raise
            raise AssertionError("unreachable")

    with pytest.raises(RunCeilingReachedError):
        await scope.next_event(_StepLongerThanTheRun())

    assert cancelled is True


@pytest.mark.asyncio
async def test_a_step_that_swallows_the_ceiling_starts_no_further_step() -> None:
    """A step may swallow the deadline's cancellation and return its value. The
    accepted cost is that one step: the run ends before the next one starts."""

    scope = RunScope(RunLimits(wall_clock_seconds=0.05))
    steps = 0

    class _StepThatSwallowsCancellation:
        def __aiter__(self) -> "_StepThatSwallowsCancellation":
            return self

        async def __anext__(self) -> object:
            nonlocal steps
            steps += 1
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return "swallowed"
            return "slept"

    assert await scope.next_event(_StepThatSwallowsCancellation()) == "swallowed"

    with pytest.raises(RunCeilingReachedError):
        await scope.next_event(_StepThatSwallowsCancellation())
    assert steps == 1


# ---------------------------------------------------------------------------
# The scope itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_children_are_bounded_to_the_configured_number() -> None:
    scope = RunScope(RunLimits(wall_clock_seconds=30.0, max_concurrent_children=2))
    live = 0
    peak = 0

    async def _child() -> int:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return live

    await scope.run_children([_child for _ in range(6)])

    assert peak == 2


@pytest.mark.asyncio
async def test_a_nested_child_fails_promptly_when_the_bound_is_in_use() -> None:
    scope = RunScope(RunLimits(wall_clock_seconds=30.0, max_concurrent_children=1))

    async with scope.child_slot():
        with pytest.raises(ChildLimitReachedError):
            async with scope.child_slot():
                raise AssertionError("unreachable")


class _InvokingGraphAgent(GraphAgentDefinition):
    target_agent_id: str
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="invoke",
            nodes=(GraphNodeDefinition(node_id="invoke", title="Invoke"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(self, input_model: BaseModel, binding: object) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        target = self.target_agent_id

        async def _invoke(state: BaseModel, ctx: Any) -> GraphNodeResult:
            del state
            await ctx.invoke_agent(target, "continue")
            return GraphNodeResult()

        return {"invoke": _invoke}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


class _LeafGraphAgent(_InvokingGraphAgent):
    target_agent_id: str = "unused"

    def node_handlers(self) -> Mapping[str, object]:
        async def _finish(state: BaseModel, ctx: Any) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult()

        return {"invoke": _finish}


async def _run_nested_registry_graph(max_children: int) -> list[RuntimeEvent]:
    configure_run_limits(wall_clock_seconds=2.0, max_concurrent_children=max_children)
    leaf = _LeafGraphAgent(agent_id="leaf")
    child = _InvokingGraphAgent(agent_id="child", target_agent_id="leaf")
    registry = {"child": child, "leaf": leaf}
    invoker = LocalRegistryAgentInvoker(registry=registry, access_token=None)
    parent = _InvokingGraphAgent(agent_id="parent", target_agent_id="child")
    runtime = GraphRuntime(
        definition=parent,
        services=RuntimeServices(agent_invoker=cast(Any, invoker)),
    )
    executor = await runtime.build_executor(binding(parent.agent_id))
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://test.invalid"))
    )
    try:
        return [
            event
            async for event in executor.stream(
                _GraphInput(message="start"), ExecutionConfig(session_id="nested")
            )
        ]
    finally:
        set_runtime_context(None)


@pytest.mark.asyncio
async def test_nested_registry_graph_reports_the_child_limit_without_waiting() -> None:
    events = await asyncio.wait_for(_run_nested_registry_graph(1), timeout=1.0)

    assert terminal_event(events).reason is RuntimeStopReason.CHILD_LIMIT_REACHED


@pytest.mark.asyncio
async def test_nested_registry_graph_completes_when_each_child_fits_the_bound() -> None:
    events = await asyncio.wait_for(_run_nested_registry_graph(2), timeout=1.0)

    assert isinstance(events[-1], FinalRuntimeEvent)
    assert not any(isinstance(event, RuntimeErrorEvent) for event in events)


@pytest.mark.asyncio
async def test_a_nested_run_joins_the_parents_budget() -> None:
    configure_run_limits(wall_clock_seconds=30.0)

    with RunScope.open(agent_id="parent") as parent:
        with RunScope.open(agent_id="child") as child:
            # A child that opened its own budget could outlive the run that
            # started it, which is what the ceiling exists to prevent.
            assert child is parent


@pytest.mark.asyncio
async def test_an_exhausted_scope_refuses_to_go_on() -> None:
    scope = RunScope(
        RunLimits(wall_clock_seconds=1.0), clock=lambda: 2.0, started_at=0.0
    )

    with pytest.raises(RunCeilingReachedError) as caught:
        scope.raise_if_exhausted()

    assert caught.value.reason == "run_ceiling_reached"


def test_a_recorded_stop_is_raised_as_a_fresh_error_each_time() -> None:
    """One shared instance re-raised from several sites accumulates a traceback
    that belongs to none of them."""

    scope = RunScope(RunLimits(wall_clock_seconds=30.0))
    recorded = AuthorityLostError()
    scope.record_stop(recorded)

    raised = []
    for _ in range(2):
        with pytest.raises(AuthorityLostError) as caught:
            scope.raise_if_stopped()
        raised.append(caught.value)

    assert raised[0] is not recorded
    assert raised[1] is not recorded
    assert raised[0] is not raised[1]
    assert raised[0].reason == "authority_lost"


@pytest.mark.parametrize("reason", list(RuntimeStopReason))
def test_every_reason_has_its_own_platform_sentence(reason: RuntimeStopReason) -> None:
    """A reason added to the contract without a sentence beside it fails here,
    where it is cheap, rather than reading as a cancelled run in production."""

    class _Stop(RunStopError):
        pass

    _Stop.reason = reason.value
    event = terminal_stop_event(_Stop())

    assert event.reason is reason
    assert event.message == _STOP_MESSAGES[reason]


def test_a_reason_with_no_sentence_still_ends_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler that ends runs must not be the one that raises: looking the
    sentence up directly would `KeyError` exactly there."""

    monkeypatch.delitem(_STOP_MESSAGES, RuntimeStopReason.AUTHORITY_LOST)

    event = terminal_stop_event(AuthorityLostError())

    assert event.reason is RuntimeStopReason.AUTHORITY_LOST
    assert event.message == _STOP_MESSAGES[RuntimeStopReason.CANCELLED]


@pytest.mark.asyncio
async def test_a_child_is_registered_on_the_run_that_is_open() -> None:
    """The registration point a spawn path calls: work started in a task of its
    own goes with the run, and a caller outside any run is told so."""

    async def _forever() -> None:
        await asyncio.sleep(3600)

    orphan = asyncio.ensure_future(_forever())
    try:
        assert register_run_child(cast(Any, orphan)) is False
    finally:
        orphan.cancel()

    with RunScope.open(agent_id="parent") as scope:
        child = asyncio.ensure_future(_forever())
        assert register_run_child(cast(Any, child)) is True
        scope.cancel_children()

    await asyncio.sleep(0)
    assert child.cancelled()


# ---------------------------------------------------------------------------
# ReAct engine
# ---------------------------------------------------------------------------


class _SlowCompiledAgent:
    """Streams nothing and keeps working past any ceiling."""

    def __init__(self) -> None:
        self.cancelled = False

    def astream(self, *_args: object, **_kwargs: object) -> AsyncIterator[object]:
        async def _generate() -> AsyncIterator[object]:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            yield ("updates", {})

        return _generate()


async def _run_react_stream(agent: object) -> list[RuntimeEvent]:
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="ReActRuntime",
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )
    collected: list[RuntimeEvent] = []
    async for event in executor.stream(input_model, ExecutionConfig(session_id="s")):
        collected.append(event)
    return collected


@pytest.mark.asyncio
async def test_react_run_past_its_ceiling_ends_typed() -> None:
    configure_run_limits(wall_clock_seconds=0.05)
    agent = _SlowCompiledAgent()

    events = await _run_react_stream(agent)

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.RUN_CEILING_REACHED
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)
    # The work in flight when the budget ran out is cancelled, not abandoned.
    assert agent.cancelled is True


@pytest.mark.asyncio
async def test_react_run_under_its_ceiling_is_untouched() -> None:
    configure_run_limits(wall_clock_seconds=30.0)

    class _PromptAgent:
        def astream(self, *_args: object, **_kwargs: object) -> AsyncIterator[object]:
            async def _generate() -> AsyncIterator[object]:
                # Longer than a tight per-call read timeout would allow, and far
                # inside the run's own budget.
                await asyncio.sleep(0.05)
                yield (
                    "updates",
                    {"model": {"messages": [AIMessage(content="all good")]}},
                )

            return _generate()

    events = await _run_react_stream(_PromptAgent())

    # The anchor: the turn really answered. Without it this test passes on a
    # run that produced nothing at all, which is the failure it exists to catch.
    finals = [event for event in events if isinstance(event, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert finals[0].content == "all good"
    assert not any(isinstance(event, RuntimeErrorEvent) for event in events)


# ---------------------------------------------------------------------------
# Graph engine
# ---------------------------------------------------------------------------


SLOW_NODE: dict[str, bool] = {}


class _GraphInput(BaseModel):
    message: str = ""


class _GraphState(BaseModel):
    message: str = ""


class _SlowGraphAgent(GraphAgentDefinition):
    agent_id: str = "test.graph.ceiling"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="slow",
            nodes=(GraphNodeDefinition(node_id="slow", title="Slow"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(self, input_model: BaseModel, binding: Any) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        async def _slow(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                SLOW_NODE["cancelled"] = True
                raise
            return GraphNodeResult()

        return {"slow": _slow}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


@pytest.mark.asyncio
async def test_graph_run_past_its_ceiling_ends_typed() -> None:
    configure_run_limits(wall_clock_seconds=0.05)
    SLOW_NODE.clear()
    definition = _SlowGraphAgent()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    executor = await runtime.build_executor(binding(definition.agent_id))

    collected: list[RuntimeEvent] = []
    async for event in executor.stream(
        _GraphInput(message="hi"), ExecutionConfig(session_id="s")
    ):
        collected.append(event)

    terminal = terminal_event(collected)
    assert terminal.reason is RuntimeStopReason.RUN_CEILING_REACHED
    assert not any(isinstance(event, FinalRuntimeEvent) for event in collected)
    assert SLOW_NODE.get("cancelled") is True
