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

"""`GraphExecutor` against the real SQL checkpointer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from fred_runtime.graph.graph_executor import GraphExecutor
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.runtime_support.checkpoints import graph_thread_prefix
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, typed_node
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
    RuntimeServices,
)
from fred_sdk.graph.runtime import GraphNodeContext
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine


class _Input(BaseModel):
    message: str = Field(..., min_length=1)


class _State(BaseModel):
    latest_user_text: str
    final_text: str | None = None


@typed_node(_State)
async def _answer(state: _State, context: GraphNodeContext) -> StepResult:
    return StepResult(state_update={"final_text": f"ok: {state.latest_user_text}"})


class _Agent(GraphAgent):
    agent_id: str = "fred.tests.storage"
    role: str = "Storage probe"
    description: str = "One-node graph used to inspect what the engine stores."
    input_schema = _Input
    state_schema = _State
    input_to_state = {"message": "latest_user_text"}
    workflow = GraphWorkflow(entry="answer", nodes={"answer": _answer})


@pytest_asyncio.fixture
async def checkpointer(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cp.sqlite3'}")
    yield FredSqlCheckpointer(engine, prefix="v2_")
    await engine.dispose()


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s1", user_id="alice", team_id="t1"),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="c1",
            actor="alice",
            tenant="t1",
            environment=PortableEnvironment.DEV,
            session_id="s1",
            user_id="alice",
            team_id="t1",
            baggage={"agent_instance_id": "inst-1"},
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True])
async def test_final_output_belongs_to_its_run_when_another_replica_advances_thread(
    checkpointer: FredSqlCheckpointer,
    monkeypatch: pytest.MonkeyPatch,
    streamed: bool,
) -> None:
    runtimes = [
        GraphRuntime(
            definition=_Agent(), services=RuntimeServices(checkpointer=checkpointer)
        )
        for _ in range(2)
    ]
    for runtime in runtimes:
        runtime.bind(_binding())
    first, second = [
        cast(GraphExecutor, await runtime.get_executor()) for runtime in runtimes
    ]
    original_stream = first._compiled.astream
    competing_outputs: list[BaseModel] = []

    async def advance_thread_after_stream(
        *args: Any, **kwargs: Any
    ) -> AsyncIterator[Any]:
        async for event in original_stream(*args, **kwargs):
            yield event
        competing_outputs.append(
            await second.invoke(
                _Input(message="second"), ExecutionConfig(session_id="s1")
            )
        )

    monkeypatch.setattr(first._compiled, "astream", advance_thread_after_stream)
    config = ExecutionConfig(session_id="s1")
    if streamed:
        events = [
            event async for event in first.stream(_Input(message="first"), config)
        ]
        assert isinstance(events[-1], FinalRuntimeEvent)
        assert events[-1].content == "ok: first"
    else:
        output = await first.invoke(_Input(message="first"), config)
        assert output.model_dump()["content"] == "ok: first"
    assert competing_outputs[0].model_dump()["content"] == "ok: second"


@pytest.mark.asyncio
async def test_native_graph_threads_record_their_owner_and_purge_with_the_session(
    checkpointer: FredSqlCheckpointer,
) -> None:
    runtime = GraphRuntime(
        definition=_Agent(),
        services=RuntimeServices(checkpointer=checkpointer),
    )
    runtime.bind(_binding())
    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _Input(message="hi"), ExecutionConfig(session_id="s1")
        )
    ]
    assert isinstance(events[-1], FinalRuntimeEvent)
    assert events[-1].content == "ok: hi"

    owners = await checkpointer.session_thread_owners(
        "s1", derived_prefix=graph_thread_prefix("s1")
    )
    assert owners == {"s1:inst-1": "alice"}

    assert (
        await checkpointer.adelete_session_threads(
            "s1", derived_prefix=graph_thread_prefix("s1")
        )
        > 0
    )
    assert (
        await checkpointer.session_thread_owners(
            "s1", derived_prefix=graph_thread_prefix("s1")
        )
        == {}
    )


@typed_node(_State)
async def _two_questions(state: _State, context: GraphNodeContext) -> StepResult:
    first = await context.request_human_input(HumanInputRequest(stage="first"))
    second = await context.request_human_input(HumanInputRequest(stage="second"))
    return StepResult(state_update={"final_text": f"{first}+{second}"})


class _TwoQuestionAgent(_Agent):
    workflow = GraphWorkflow(entry="ask", nodes={"ask": _two_questions})


@pytest.mark.asyncio
async def test_each_question_of_one_node_takes_its_own_resume_claim(
    checkpointer: FredSqlCheckpointer,
) -> None:
    # LangGraph gives every interrupt() of one task the same Interrupt.id, so
    # the claim that makes a resume single-use must also key on the occurrence.
    async def turn(config: ExecutionConfig) -> list:
        runtime = GraphRuntime(
            definition=_TwoQuestionAgent(),
            services=RuntimeServices(checkpointer=checkpointer),
        )
        runtime.bind(_binding())
        executor = await runtime.get_executor()
        return [event async for event in executor.stream(_Input(message="go"), config)]

    async def answer(pause: AwaitingHumanRuntimeEvent, value: str) -> list:
        request = pause.request
        assert request.interrupt_id is not None
        identity = {
            "thread_id": "s1:inst-1",
            "checkpoint_ns": "",
            "interrupt_id": request.interrupt_id,
            "occurrence_id": request.occurrence_id,
        }
        token = await checkpointer.aclaim_hitl_resume(**identity)
        assert token is not None, f"resume of {request.stage!r} was refused"
        assert await checkpointer.astart_hitl_resume(**identity, claim_token=token)
        events = await turn(
            ExecutionConfig(
                session_id="s1",
                interrupt_id=request.interrupt_id,
                resume_payload=value,
            )
        )
        await checkpointer.aconsume_hitl_resume(**identity, claim_token=token)
        return events

    first = await turn(ExecutionConfig(session_id="s1"))
    assert isinstance(first[-1], AwaitingHumanRuntimeEvent)
    second = await answer(first[-1], "a")
    assert isinstance(second[-1], AwaitingHumanRuntimeEvent)
    assert second[-1].request.stage == "second"
    final = await answer(second[-1], "b")
    assert isinstance(final[-1], FinalRuntimeEvent)
    assert final[-1].content == "a+b"
