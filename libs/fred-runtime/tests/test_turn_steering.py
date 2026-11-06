"""History-backed in-thread user messages across runtime replicas."""

import asyncio

import pytest
from fred_core.history.history_schema import ChatMessage, TextPart, make_user_text
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from fred_runtime.runtime_support import turn_steering
from fred_sdk.contracts.models import GraphAgentDefinition
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from sqlalchemy.ext.asyncio import create_async_engine


async def _replicas(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'steering.sqlite'}"
    first_engine = create_async_engine(url)
    second_engine = create_async_engine(url)
    await create_history_schema(first_engine)
    return (
        PostgresHistoryStore(first_engine),
        PostgresHistoryStore(second_engine),
        first_engine,
        second_engine,
    )


def _text(message: ChatMessage) -> str:
    part = message.parts[0]
    assert isinstance(part, TextPart)
    return part.text


class _UnusedGraph(GraphAgentDefinition):
    agent_id: str = "test.graph"
    role: str = "test"
    description: str = "test"

    def build_graph(self):
        raise NotImplementedError

    def input_model(self):
        raise NotImplementedError

    def state_model(self):
        raise NotImplementedError

    def output_model(self):
        raise NotImplementedError

    def build_initial_state(self, input_model, binding):
        raise NotImplementedError

    def build_output(self, state):
        raise NotImplementedError

    def node_handlers(self):
        raise NotImplementedError


def test_graph_fallback_acknowledges_at_hitl_pause_once():
    from fred_runtime.app.agent_app import _AgentExecuteRequest, _TurnEventExpander

    expander = _TurnEventExpander(
        _UnusedGraph(),
        _AgentExecuteRequest(
            agent_id="test.graph", message="new turn", pending_message_id="m1"
        ),
    )
    expanded = expander.expand({"kind": "awaiting_human", "request": {}})
    assert [payload["kind"] for payload in expanded] == [
        "steered_user_message",
        "awaiting_human",
    ]
    assert expander.expand({"kind": "final"}) == [{"kind": "final"}]


@pytest.mark.asyncio
async def test_submission_is_durable_ordered_and_idempotent_across_replicas(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        first_row = await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="first",
        )
        second_row = await second.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m2",
            content="second",
        )
        retry = await second.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="first",
        )
        assert (first_row.rank, second_row.rank, retry.rank) == (-1, -2, -1)
        assert first_row.exchange_id == retry.exchange_id == "pending:m1"
        assert second_row.exchange_id == "pending:m2"
        assert [
            _text(row) for row in await first.pending_steered_messages("s", "u")
        ] == [
            "first",
            "second",
        ]
        with pytest.raises(ValueError, match="message_id_reused"):
            await second.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id="m1",
                content="different",
            )
        delivered = await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=0,
            exchange_id="ex",
            expected_content="first",
        )
        assert delivered is not None and delivered.rank == 0
        assert delivered.exchange_id == "ex"
        assert [
            row.rank for row in await second.pending_steered_messages("s", "u")
        ] == [-2]
        assert [row.rank for row in await second.get("s", "u")] == [-2, 0]
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_submission_normalizes_nul_before_storage_and_retry(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        kwargs = dict(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="a\x00b",
        )
        first_row = await first.submit_steered_message(**kwargs)
        retry = await second.submit_steered_message(**kwargs)
        assert _text(first_row) == _text(retry) == "a[U+0000]b"
        normalization = (first_row.metadata.model_extra or {}).get(
            "history_text_normalization"
        )
        assert isinstance(normalization, dict)
        assert normalization["count"] == 1
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_submissions_keep_distinct_provisional_ranks(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:

        async def submit(store, message_id):
            return await store.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id=message_id,
                content=message_id,
            )

        rows = await asyncio.gather(submit(first, "m1"), submit(second, "m2"))
        assert {row.rank for row in rows} == {-1, -2}
        assert len(await first.pending_steered_messages("s", "u")) == 2
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_middleware_injects_and_emits_delivery_at_model_boundary(
    monkeypatch, tmp_path
):
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="focus on Marseille",
        )
        middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        update = await middleware.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None
        injected = update["messages"][0]
        assert isinstance(injected, HumanMessage)
        assert injected.id == "steered:m1"
        assert isinstance(injected.content, str) and injected.content.endswith(
            "focus on Marseille"
        )
        assert [(event.message_id, event.content) for event in events] == [
            ("m1", "focus on Marseille")
        ]
        await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=1,
            exchange_id="ex",
            expected_content="focus on Marseille",
        )
        assert (
            await middleware.abefore_model(
                {"messages": [injected]}, Runtime(context=None)
            )
            is None
        )
        assert len(events) == 1
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_checkpoint_replay_emits_ack_once_and_recovery_keeps_identity(
    monkeypatch, tmp_path
):
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="new instruction",
        )
        checkpoint_message = HumanMessage(id="steered:m1", content="new instruction")
        middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        assert (
            await middleware.abefore_model(
                {"messages": [checkpoint_message]}, Runtime(context=None)
            )
            is None
        )
        assert [event.message_id for event in events] == ["m1"]
        await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=1,
            exchange_id="ex",
        )
        await first.save(
            "s",
            [make_user_text("s", "ex", 2, "trace committed before the checkpoint")],
            "u",
        )
        recovery = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        update = await recovery.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None
        assert update["messages"][0].id == "steered:m1"
        assert [event.message_id for event in events] == ["m1"]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_fallback_ack_uses_opening_rank_and_trace_keeps_rank_order(
    monkeypatch, tmp_path
):
    from fred_runtime.app.agent_app import (
        _HistoryRanker,
        _opening_history_count,
        _rank_runtime_event,
        _write_turn_history,
    )

    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    store, _, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(store)
    try:
        await store.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="new turn",
        )
        middleware = turn_steering.TurnSteeringMiddleware(
            "s", pending_message_id="m1", exchange_id="ex"
        )
        assert (
            await middleware.abefore_model({"messages": []}, Runtime(context=None))
            is None
        )
        assert [event.message_id for event in events] == ["m1"]
        payloads = [
            {"kind": "steered_user_message", "message_id": "m1", "content": "new turn"},
            {
                "kind": "tool_call",
                "call_id": "c1",
                "tool_name": "lookup",
                "arguments": {},
            },
            {"kind": "tool_result", "call_id": "c1", "content": "done"},
            {"kind": "final", "content": "answer"},
        ]
        ranker = _HistoryRanker(
            _opening_history_count("new turn", None),
            opening_rank=0,
            previously_pending_occurrence_ids=(),
            pending_message_id="m1",
        )
        payloads = [
            await _rank_runtime_event(
                payload,
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )
            for payload in payloads
        ]
        assert [payload["rank"] for payload in payloads] == [0, 1, 2, 3]
        await _write_turn_history(
            session_id="s",
            user_id="u",
            request_message="new turn",
            payloads=payloads,
            history_store=store,
            exchange_id="ex",
            base_rank=0,
            pending_message_id="m1",
        )
        rows = await store.get("s", "u")
        assert [(row.rank, row.channel.value) for row in rows] == [
            (0, "final"),
            (1, "tool_call"),
            (2, "tool_result"),
            (3, "final"),
        ]
        assert [_text(row) for row in rows if row.role.value == "user"] == ["new turn"]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()
