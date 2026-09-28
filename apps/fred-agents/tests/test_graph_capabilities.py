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
Graph capabilities: what LangGraph gives Fred graph agents, and what it
offers that they do not reach yet.

Each test states one behavior. A gap is marked `xfail(strict=True)`: it stays
on record without breaking the suite, and the day the capability lands the
test XPASSes, which fails strict mode — remove the marker then.
"""

from __future__ import annotations

import asyncio

import pytest
from fred_agents.test_assistant.mock_llm import MockChatModel, MockChatModelFactory
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, model_text_step, typed_node
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    HumanInputRequest,
    RuntimeEvent,
    RuntimeServices,
    StatusRuntimeEvent,
    ThoughtStartEvent,
)
from fred_sdk.graph.authoring.api import WorkflowNode
from fred_sdk.graph.runtime import GraphNodeContext
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field


class _Input(BaseModel):
    message: str = Field(..., min_length=1)


class _State(BaseModel):
    latest_user_text: str
    left: str = ""
    right: str = ""
    attempts: int = 0
    final_text: str | None = None
    node_error: str = ""


def _agent(workflow: GraphWorkflow) -> GraphAgent:
    class _Agent(GraphAgent):
        agent_id: str = "fred.tests.capability"
        role: str = "Capability probe"
        description: str = "Probe graph for one LangGraph capability."
        input_schema = _Input
        state_schema = _State
        input_to_state = {"message": "latest_user_text"}

    _Agent.workflow = workflow
    return _Agent()


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s1", user_id="u1", team_id="t1"),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="c1",
            actor="u1",
            tenant="t1",
            environment=PortableEnvironment.DEV,
            session_id="s1",
            user_id="u1",
            team_id="t1",
        ),
    )


class _Runner:
    def __init__(self, agent: GraphAgent, model: MockChatModel | None = None):
        self._agent = agent
        self._services = RuntimeServices(
            chat_model_factory=MockChatModelFactory(model), checkpointer=InMemorySaver()
        )

    async def turn(
        self, config: ExecutionConfig, message: str = "go"
    ) -> list[RuntimeEvent]:
        runtime = GraphRuntime(
            definition=self._agent,
            services=self._services,
        )
        runtime.bind(_binding())
        executor = await runtime.get_executor()
        return [
            event async for event in executor.stream(_Input(message=message), config)
        ]

    async def resume(
        self, pause: AwaitingHumanRuntimeEvent, answer: str
    ) -> list[RuntimeEvent]:
        return await self.turn(
            ExecutionConfig(
                session_id="s1",
                interrupt_id=pause.request.interrupt_id,
                resume_payload={"choice_id": answer},
            )
        )


def _final_text(events: list[RuntimeEvent]) -> str:
    final = events[-1]
    assert isinstance(final, FinalRuntimeEvent), events[-3:]
    return final.content


def _done(text: str):
    @typed_node(_State)
    async def step(state: _State, context: GraphNodeContext) -> StepResult:
        return StepResult(
            state_update={"final_text": text.format(**state.model_dump())}
        )

    return step


# ── several human questions in one node ─────────────────────────────────────


def _choice(answer: object) -> object:
    return answer.get("choice_id") if isinstance(answer, dict) else answer


@typed_node(_State)
async def _two_questions(state: _State, context: GraphNodeContext) -> StepResult:
    first = await context.request_human_input(HumanInputRequest(stage="first"))
    second = await context.request_human_input(HumanInputRequest(stage="second"))
    return StepResult(
        state_update={"final_text": f"{_choice(first)}+{_choice(second)}"}
    )


@pytest.mark.asyncio
async def test_one_node_can_ask_several_questions() -> None:
    runner = _Runner(_agent(GraphWorkflow(entry="ask", nodes={"ask": _two_questions})))
    first = await runner.turn(ExecutionConfig(session_id="s1"))
    assert isinstance(first[-1], AwaitingHumanRuntimeEvent)
    assert first[-1].request.stage == "first"
    second = await runner.resume(first[-1], "a")
    assert isinstance(second[-1], AwaitingHumanRuntimeEvent), second[-2:]
    assert second[-1].request.stage == "second"
    assert _final_text(await runner.resume(second[-1], "b")) == "a+b"


# ── parallel fan-out ─────────────────────────────────────────────────────────


@typed_node(_State)
async def _noop(state: _State, context: GraphNodeContext) -> StepResult:
    return StepResult()


@typed_node(_State)
async def _left(state: _State, context: GraphNodeContext) -> StepResult:
    await asyncio.sleep(0.01)
    return StepResult(state_update={"left": "L"})


@typed_node(_State)
async def _right(state: _State, context: GraphNodeContext) -> StepResult:
    return StepResult(state_update={"right": "R"})


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="CAPABILITY parallel: LangGraph runs fan-out branches in one superstep "
    "(Send / multi-target Command); the authoring API cannot declare them",
)
async def test_parallel_branches_run_in_one_superstep() -> None:
    workflow = GraphWorkflow(
        entry="start",
        nodes={
            "start": _noop,
            "left": _left,
            "right": _right,
            "join": _done("{left}{right}"),
        },
        parallel={"start": ("join", ["left", "right"])},  # type: ignore[call-arg]
    )
    runner = _Runner(_agent(workflow))
    assert _final_text(await runner.turn(ExecutionConfig(session_id="s1"))) == "LR"


# ── retries and timeouts per node ───────────────────────────────────────────


@typed_node(_State)
async def _flaky(state: _State, context: GraphNodeContext) -> StepResult:
    raise ConnectionError("transient upstream failure")


@typed_node(_State)
async def _hangs(state: _State, context: GraphNodeContext) -> StepResult:
    await asyncio.sleep(30)
    return StepResult()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="CAPABILITY retry: LangGraph RetryPolicy retries a node on transient "
    "errors before on_error; the authoring API cannot declare one",
)
async def test_a_node_declares_a_retry_policy() -> None:
    node = WorkflowNode(handler=_flaky, retry_attempts=3)  # type: ignore[call-arg]
    workflow = GraphWorkflow(entry="call", nodes={"call": node})
    runner = _Runner(_agent(workflow))
    await runner.turn(ExecutionConfig(session_id="s1"))


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="CAPABILITY timeout: LangGraph TimeoutPolicy (run/idle) fails a hung "
    "node into its on_error route; the authoring API cannot declare one",
)
async def test_a_hung_node_times_out_into_its_error_route() -> None:
    node = WorkflowNode(handler=_hangs, timeout_s=0.2)  # type: ignore[call-arg]
    workflow = GraphWorkflow(
        entry="call",
        nodes={"call": node, "finalize": _done("timed out: {node_error}")},
        error_routes={"call": "finalize"},
    )
    runner = _Runner(_agent(workflow))
    text = await asyncio.wait_for(runner.turn(ExecutionConfig(session_id="s1")), 5)
    assert _final_text(text).startswith("timed out")


# ── progress and reasoning the UI could show for free ───────────────────────


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="CAPABILITY progress: LangGraph's 'tasks' stream reports every node "
    "start/finish; Fred shows nothing for a node whose author emits no status",
)
async def test_every_node_reports_its_progress() -> None:
    workflow = GraphWorkflow(entry="silent_work", nodes={"silent_work": _done("done")})
    events = await _Runner(_agent(workflow)).turn(ExecutionConfig(session_id="s1"))
    assert any(
        isinstance(e, StatusRuntimeEvent) and "silent" in (e.detail or "").lower()
        for e in events
    )


@typed_node(_State)
async def _ask_model(state: _State, context: GraphNodeContext) -> StepResult:
    text = await model_text_step(context, user_prompt=state.latest_user_text)
    return StepResult(state_update={"final_text": text})


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="CAPABILITY reasoning: a graph node's model call drops model-native "
    "reasoning that ReAct surfaces as THOUGHT events (source=model_native)",
)
async def test_model_native_reasoning_reaches_the_ui() -> None:
    workflow = GraphWorkflow(entry="ask", nodes={"ask": _ask_model})
    runner = _Runner(_agent(workflow), MockChatModel(emit_reasoning=True))
    events = await runner.turn(ExecutionConfig(session_id="s1"), "why")
    assert any(
        isinstance(e, ThoughtStartEvent) and e.source == "model_native" for e in events
    )


# ── upstream: native node error handler under streaming ─────────────────────


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="UPSTREAM langgraph 1.2.12: add_node(error_handler=...) recovers, but "
    "astream re-raises the handled error whenever stream_mode includes 'custom' "
    "(fine with 'updates'/'values' alone). When this passes, map on_error to "
    "error_handler in graph_executor.py",
)
async def test_native_node_error_handler_recovers_under_astream() -> None:
    from typing import TypedDict

    from langgraph.errors import NodeError
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    class State(TypedDict, total=False):
        done: str

    async def boom(state: State) -> State:
        raise RuntimeError("boom")

    async def handler(state: State, error: NodeError) -> Command:
        return Command(goto="recover")

    async def recover(state: State) -> State:
        return {"done": "recovered"}

    builder = StateGraph(State)
    # langgraph types error_handler as a plain node; it is called with the error.
    builder.add_node("boom", boom, error_handler=handler)  # pyright: ignore[reportArgumentType]
    builder.add_node("recover", recover)
    builder.add_edge(START, "boom")
    builder.add_edge("recover", END)
    graph = builder.compile()
    # "custom" is the mode Fred's executor streams node events through.
    chunks = [
        chunk async for chunk in graph.astream({}, stream_mode=["updates", "custom"])
    ]
    assert ("updates", {"recover": {"done": "recovered"}}) in chunks
