"""History-backed in-thread user messages across runtime replicas."""

import asyncio
from typing import Any, cast

import pytest
from fred_core.history.history_schema import ChatMessage, TextPart, make_user_text
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
    steered_reply_id,
)
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.runtime_context import (
    RuntimeConfig,
    set_runtime_context,
)
from fred_runtime.runtime_context import (
    RuntimeContext as FredRuntimeContext,
)
from fred_runtime.runtime_support import turn_steering
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.models import GraphAgentDefinition
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
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


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_runtime_steering_gate_reaches_middleware_binding(monkeypatch, enabled):
    class BindingCaptured(Exception):
        pass

    captured: dict[str, Any] = {}

    def capture_binding(_definition, binding, **_kwargs):
        captured["binding"] = binding
        raise BindingCaptured

    monkeypatch.setattr(agent_app_module, "_build_runtime_services", capture_binding)
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid"))
    )
    try:
        request = agent_app_module._AgentExecuteRequest.model_construct(
            agent_id="test.graph",
            message="hello",
            context={"session_id": "s", "steering_enabled": "true"},
        )
        with pytest.raises(BindingCaptured):
            await anext(
                agent_app_module._iterate_runtime_event_payloads_inner(
                    _UnusedGraph(), request, steering_enabled=enabled
                )
            )
        assert captured["binding"].portable_context.baggage.get("steering_enabled") == (
            "true" if enabled else None
        )
    finally:
        set_runtime_context(None)


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
        assert events == []
        assert middleware._pending_delivery == (("m1", "focus on Marseille"),)
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
        assert events == []
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
        assert events == []
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
        assert events == []
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


@pytest.mark.asyncio
async def test_steered_reply_is_visible_before_normal_model_call(monkeypatch):
    events = []
    scope_holder = []

    def write(event):
        events.append(event)
        if getattr(event, "kind", None) == "steered_assistant_message":
            scope_holder[0].complete_event_receipt(
                steered_reply_id(("m1",)), {"content": event.content}
            )

    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: write)
    middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
    middleware._unanswered_ids = ("m1",)
    middleware._pending_delivery = (("m1", "Where are you?"),)
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            assert request.tools == []
            assert request.response_format is None
            return ModelResponse(
                result=[AIMessage(content="I am checking the sources.")]
            )
        assert request.messages[-1].content == "I am checking the sources."
        return ModelResponse(result=[AIMessage(content="Continuing work.")])

    with RunScope.open() as scope:
        scope_holder.append(scope)
        response = await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[HumanMessage(content="Where are you?")],
            ),
            handler,
        )
    assert [message.content for message in response.result] == [
        "I am checking the sources.",
        "Continuing work.",
    ]
    assert response.result[0].id == steered_reply_id(("m1",))
    assert events[0] == {"kind": "_steered_reply_start"}
    assert events[1].message_ids == ("m1",)
    assert events[1].deliveries[0].message_id == "m1"
    assert events[1].content == "I am checking the sources."


@pytest.mark.asyncio
async def test_failed_steered_reply_does_not_emit_delivery(monkeypatch):
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
    middleware._unanswered_ids = ("m1",)
    middleware._pending_delivery = (("m1", "Where are you?"),)

    async def empty_reply(_request):
        return ModelResponse(result=[AIMessage(content="")])

    with pytest.raises(RuntimeError, match="Steered assistant reply was empty"):
        await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[HumanMessage(content="Where are you?")],
            ),
            empty_reply,
        )
    assert events == [{"kind": "_steered_reply_start"}]


@pytest.mark.asyncio
async def test_steered_reply_recovery_keeps_message_order(monkeypatch, tmp_path):
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: None)
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="status?",
        )
        await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=1,
            exchange_id="ex",
            expected_content="status?",
        )
        _, reply = await first.persist_steered_assistant_message(
            session_id="s",
            user_id="u",
            exchange_id="ex",
            rank=2,
            message_ids=("m1",),
            content="Still checking.",
        )
        _, repeated = await second.persist_steered_assistant_message(
            session_id="s",
            user_id="u",
            exchange_id="ex",
            rank=3,
            message_ids=("m1",),
            content="Duplicate.",
        )
        assert repeated.rank == reply.rank == 2
        recovered = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        update = await recovered.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None
        assert [item.id for item in update["messages"]] == [
            "steered:m1",
            steered_reply_id(("m1",)),
        ]
        assert update["messages"][1].additional_kwargs == {"steered_reply_for": ["m1"]}
        assert recovered._unanswered_ids == ()
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_reply_and_user_promotion_commit_atomically_across_replicas(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="status?",
        )
        with pytest.raises(ValueError, match="pending_message_unavailable"):
            await second.persist_steered_assistant_message(
                session_id="s",
                user_id="u",
                exchange_id="ex",
                rank=3,
                message_ids=("m1",),
                content="Checking.",
                deliveries=(("m1", "status?", 1), ("missing", "x", 2)),
            )
        still_pending = await first.pending_steered_message("s", "u", "m1")
        assert still_pending is not None and still_pending.rank == -1

        delivered, reply = await second.persist_steered_assistant_message(
            session_id="s",
            user_id="u",
            exchange_id="ex",
            rank=2,
            message_ids=("m1",),
            content="Checking.",
            deliveries=(("m1", "status?", 1),),
        )
        assert [item.rank for item in delivered] == [1]
        assert reply.rank == 2
        (
            repeated_delivery,
            repeated_reply,
        ) = await first.persist_steered_assistant_message(
            session_id="s",
            user_id="u",
            exchange_id="ex",
            rank=11,
            message_ids=("m1",),
            content="Different retry text.",
            deliveries=(("m1", "status?", 10),),
        )
        assert [item.rank for item in repeated_delivery] == [1]
        assert _text(repeated_reply) == "Checking."
        assert [item.rank for item in await first.get("s", "u")] == [1, 2]
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_reply_cannot_claim_message_delivered_to_another_exchange(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="status?",
        )
        await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=1,
            exchange_id="first-exchange",
            expected_content="status?",
        )
        with pytest.raises(
            ValueError, match="pending_message_delivered_in_another_exchange"
        ):
            await second.persist_steered_assistant_message(
                session_id="s",
                user_id="u",
                exchange_id="second-exchange",
                rank=2,
                message_ids=("m1",),
                content="Checking.",
                deliveries=(("m1", "status?", 1),),
            )
        assert [item.rank for item in await first.get("s", "u")] == [1]
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_normal_model_waits_for_reply_persistence(monkeypatch, tmp_path):
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    queue = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: queue.put_nowait)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="status?",
        )
        middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        update = await middleware.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None

        async def consume_events():
            assert await queue.get() == {"kind": "_steered_reply_start"}
            event = await queue.get()
            ranker = _HistoryRanker(
                1,
                opening_rank=0,
                pending_message_id=None,
                previously_pending_occurrence_ids=(),
            )
            return await _rank_runtime_event(
                event.model_dump(mode="json"),
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )

        calls = []

        async def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return ModelResponse(result=[AIMessage(content="Checking.")])
            rows = await first.get("s", "u")
            assert [(row.rank, _text(row)) for row in rows] == [
                (1, "status?"),
                (2, "Checking."),
            ]
            return ModelResponse(result=[AIMessage(content="Done.")])

        with RunScope.open():
            consumer = asyncio.create_task(consume_events())
            response = await asyncio.wait_for(
                middleware.awrap_model_call(
                    ModelRequest(
                        model=cast(BaseChatModel, object()),
                        messages=update["messages"],
                    ),
                    handler,
                ),
                timeout=5,
            )
            persisted_event = await consumer
        assert persisted_event["rank"] == 2
        assert persisted_event["deliveries"][0]["rank"] == 1
        assert [item.content for item in response.result] == ["Checking.", "Done."]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_user_message_cannot_claim_assistant_reply_identity(tmp_path):
    first, _, first_engine, second_engine = await _replicas(tmp_path)
    try:
        with pytest.raises(ValueError, match="reserved_message_id"):
            await first.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id=steered_reply_id(("m1",)),
                content="collision",
            )
    finally:
        await first_engine.dispose()
        await second_engine.dispose()
