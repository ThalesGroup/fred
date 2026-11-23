"""Exercise Graph's next-turn steering fallback with a real executor."""

from __future__ import annotations

import asyncio

import pytest
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from fred_runtime.app.agent_app import (
    _AgentExecuteRequest,
    _HistoryRanker,
    _rank_runtime_event,
    _TurnEventExpander,
    _write_turn_history,
)
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.runtime_support.turn_steering import turn_messages
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, typed_node
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import ExecutionConfig, RuntimeServices
from fred_sdk.graph.runtime import GraphNodeContext
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine


class _Input(BaseModel):
    message: str


class _State(BaseModel):
    latest_user_text: str
    final_text: str | None = None


ENTERED = asyncio.Event()
RELEASE = asyncio.Event()


@typed_node(_State)
async def _read(state: _State, context: GraphNodeContext) -> StepResult:
    ENTERED.set()
    await RELEASE.wait()
    return StepResult(state_update={"final_text": f"Read {state.latest_user_text}"})


class _Agent(GraphAgent):
    agent_id: str = "fred.tests.graph.steering"
    role: str = "Read-only probe"
    description: str = "Read and answer."
    input_schema = _Input
    state_schema = _State
    input_to_state = {"message": "latest_user_text"}
    workflow = GraphWorkflow(entry="read", nodes={"read": _read}, edges={})


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
            team_id="t",
        ),
    )


@pytest.mark.asyncio
async def test_graph_delivers_mid_run_steers_as_next_turn_openings(tmp_path) -> None:
    ENTERED.clear()
    RELEASE.clear()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'graph-steer.sqlite'}"
    )
    await create_history_schema(engine)
    first = PostgresHistoryStore(engine)
    second = PostgresHistoryStore(engine)
    turn_messages.configure(second)
    definition = _Agent()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(checkpointer=InMemorySaver()),
    )
    runtime.bind(_binding())
    executor = await runtime.get_executor()
    try:

        async def initial_turn() -> list[dict]:
            return [
                event.model_dump(mode="json")
                async for event in executor.stream(
                    _Input(message="the corpus"), ExecutionConfig(session_id="s")
                )
            ]

        running = asyncio.create_task(initial_turn())
        await asyncio.wait_for(ENTERED.wait(), 10)
        for message_id, content in (("m1", "status?"), ("m2", "add dates")):
            await first.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id=message_id,
                content=content,
            )
        RELEASE.set()
        first_events = await asyncio.wait_for(running, 10)
        assert first_events[-1]["kind"] == "final"
        await _write_turn_history(
            session_id="s",
            user_id="u",
            request_message="the corpus",
            payloads=first_events,
            history_store=second,
            exchange_id="ex-initial",
            base_rank=0,
        )
        assert [row.rank for row in await second.get("s", "u") if row.rank >= 0] == [
            0,
            1,
        ]
        assert [
            row.rank for row in await second.pending_steered_messages("s", "u")
        ] == [
            -1,
            -2,
        ]

        for rank, message_id, content in (
            (2, "m1", "status?"),
            (4, "m2", "add dates"),
        ):
            request = _AgentExecuteRequest.model_construct(
                agent_id=definition.agent_id,
                message=content,
                pending_message_id=message_id,
            )
            expander = _TurnEventExpander(definition, request)
            followup_events = [
                event.model_dump(mode="json")
                async for event in executor.stream(
                    _Input(message=content), ExecutionConfig(session_id="s")
                )
            ]
            expanded = [
                item for event in followup_events for item in expander.expand(event)
            ]
            assert [item["kind"] for item in expanded[-2:]] == [
                "steered_user_message",
                "final",
            ]
            ranker = _HistoryRanker(
                rank + 1,
                opening_rank=rank,
                pending_message_id=message_id,
                previously_pending_occurrence_ids=(),
            )
            ranked = [
                await _rank_runtime_event(
                    item,
                    ranker,
                    session_id="s",
                    user_id="u",
                    exchange_id=f"ex-{message_id}",
                )
                for item in expanded
            ]
            delivered = ranked[-2]
            assert delivered["rank"] == rank
            assert ranked[-1]["rank"] == rank + 1
            await _write_turn_history(
                session_id="s",
                user_id="u",
                request_message=content,
                payloads=ranked,
                history_store=second,
                exchange_id=f"ex-{message_id}",
                base_rank=rank,
                pending_message_id=message_id,
            )
        assert await second.pending_steered_messages("s", "u") == []
        assert [row.rank for row in await second.get("s", "u")] == [
            0,
            1,
            2,
            3,
            4,
            5,
        ]
    finally:
        turn_messages.configure(None)
        await engine.dispose()
