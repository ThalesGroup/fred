"""History-backed in-thread user messages across runtime replicas."""

import asyncio
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fred_core.history.history_schema import (
    ChatMessage,
    TextPart,
    make_tool_call,
    make_tool_result,
    make_user_text,
)
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
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
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
)
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.runtime import Runtime
from pydantic import Field
from sqlalchemy.ext.asyncio import create_async_engine
from weaver_fixtures import INSTANCE_ID, SPACE_ID, active_turn, local_binding


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


class _ScriptedSteeringModel(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-steering-integration"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedSteeringModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("Unexpected model call")
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


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
            agent_instance_id=INSTANCE_ID,
            message="hello",
            context={
                "session_id": "s",
                "user_id": "alice",
                "space_id": SPACE_ID,
                "steering_enabled": "true",
            },
        )
        with active_turn("test.graph", session="s"), pytest.raises(BindingCaptured):
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


@pytest.mark.parametrize("terminal_kind", ["awaiting_human", "final"])
def test_graph_fallback_acknowledges_at_terminal_boundary_once(terminal_kind):
    from fred_runtime.app.agent_app import _AgentExecuteRequest, _TurnEventExpander

    expander = _TurnEventExpander(
        _UnusedGraph(),
        _AgentExecuteRequest(
            agent_instance_id="a", message="new turn", pending_message_id="m1"
        ),
    )
    assert expander.expand({"kind": "tool_call", "call_id": "c1"}) == [
        {"kind": "tool_call", "call_id": "c1"}
    ]
    assert expander.expand({"kind": "tool_result", "call_id": "c1"}) == [
        {"kind": "tool_result", "call_id": "c1"}
    ]
    terminal = {"kind": terminal_kind, "request": {}}
    expanded = expander.expand(terminal)
    assert [payload["kind"] for payload in expanded] == [
        "steered_user_message",
        terminal_kind,
    ]
    assert expander.expand({"kind": "final"}) == [{"kind": "final"}]


@pytest.mark.asyncio
async def test_submission_is_durable_ordered_and_idempotent_across_replicas(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        first_row = await first.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="first",
        )
        second_row = await second.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m2",
            content="second",
        )
        retry = await second.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
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
                space_id="t",
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
async def test_first_opening_claim_binds_agent_before_steering(tmp_path):
    from fred_runtime.app.agent_app import _write_turn_history

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        opening = make_user_text("s", "ex", 0, "Start the task")
        assert await first.claim_initial_user_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message=opening,
        )
        assert await second.session_agent_instance_id("s") == "a"
        assert not await second.claim_initial_user_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message=opening,
        )
        with pytest.raises(ValueError, match="session_agent_mismatch"):
            await second.claim_initial_user_message(
                session_id="s",
                user_id="u",
                space_id="t",
                agent_instance_id="b",
                message=opening,
            )
        await second.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="change the task",
        )
        assert [row.rank for row in await first.get("s", "u")] == [-1, 0]
        await first.claim_initial_user_message(
            session_id="s2",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message=make_user_text("s2", "ex2", 0, "Rejected draft"),
        )
        await _write_turn_history(
            session_id="s2",
            user_id="u",
            request_message="Rejected draft",
            payloads=[{"kind": "execution_interrupted"}],
            history_store=first,
            exchange_id="ex2",
            prewritten_initial=True,
        )
        assert await second.get("s2", "u") == []
        await first.claim_initial_user_message(
            session_id="s3",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message=make_user_text("s3", "ex3", 0, "Accepted turn"),
        )
        await _write_turn_history(
            session_id="s3",
            user_id="u",
            request_message="Accepted turn",
            payloads=[{"kind": "status", "status": "working"}],
            history_store=first,
            agent_instance_id="a",
            exchange_id="ex3",
            base_rank=0,
            prewritten_initial=True,
        )
        assert [row.rank for row in await second.get("s3", "u")] == [0]
        await first.claim_initial_user_message(
            session_id="s4",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message=make_user_text("s4", "ex4", 0, "Interrupted turn"),
        )
        await second.submit_steered_message(
            session_id="s4",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m4",
            content="Later update",
        )
        await first.release_initial_user_message("s4", "u", "ex4")
        assert await second.session_agent_instance_id("s4") == "a"
        retry = await first.submit_steered_message(
            session_id="s4",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m4",
            content="Later update",
        )
        assert retry.rank == -1
        await first.save("mixed", [make_user_text("mixed", "old", 0, "Direct")], "u")
        with pytest.raises(ValueError, match="session_agent_mismatch"):
            await second.claim_initial_user_message(
                session_id="mixed",
                user_id="u",
                space_id="t",
                agent_instance_id="a",
                message=make_user_text("mixed", "new", 1, "Managed"),
            )
        await first.save(
            "mixed",
            [make_user_text("mixed", "managed", 1, "Managed")],
            "u",
            agent_instance_id="a",
        )
        with pytest.raises(ValueError, match="session_agent_mismatch"):
            await second.claim_initial_user_message(
                session_id="mixed",
                user_id="u",
                space_id="t",
                agent_instance_id="b",
                message=make_user_text("mixed", "new", 2, "Wrong agent"),
            )
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_pending_update_must_open_the_next_ordinary_turn(tmp_path):
    from fred_runtime.app.agent_app import (
        _AgentExecuteRequest,
        _require_pending_opening_message,
    )

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    try:
        await _require_pending_opening_message(
            _AgentExecuteRequest(agent_instance_id="a", message="new instruction"),
            "s",
            "u",
        )
        for message_id, content in (("m1", "first update"), ("m2", "second update")):
            await first.submit_steered_message(
                session_id="s",
                user_id="u",
                space_id="t",
                agent_instance_id="a",
                message_id=message_id,
                content=content,
            )
        for request in (
            _AgentExecuteRequest(agent_instance_id="a", message="new instruction"),
            _AgentExecuteRequest(
                agent_instance_id="a",
                message="second update",
                pending_message_id="m2",
            ),
            _AgentExecuteRequest(
                agent_instance_id="b",
                message="first update",
                pending_message_id="m1",
            ),
            _AgentExecuteRequest(
                agent_instance_id="b",
                message="new instruction",
                interrupted_action="restart",
            ),
            _AgentExecuteRequest(agent_id="test.graph", message="new instruction"),
        ):
            with pytest.raises(HTTPException) as conflict:
                await _require_pending_opening_message(request, "s", "u")
            assert conflict.value.status_code == 409
        await _require_pending_opening_message(
            _AgentExecuteRequest(
                agent_instance_id="a",
                message="first update",
                pending_message_id="m1",
            ),
            "s",
            "u",
        )
        await _require_pending_opening_message(
            _AgentExecuteRequest(
                agent_instance_id="a", message="", resume_payload={"approved": True}
            ),
            "s",
            "u",
        )
        await _require_pending_opening_message(
            _AgentExecuteRequest(
                agent_instance_id="a",
                message="first update",
                interrupted_action="restart",
            ),
            "s",
            "u",
        )
        await _require_pending_opening_message(
            _AgentExecuteRequest(
                agent_instance_id="a", message="", interrupted_action="continue"
            ),
            "s",
            "u",
        )
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_steer_submission_is_bound_to_session_agent(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="first",
        )
        assert len(await second.pending_steered_messages("s", "u", "a")) == 1
        assert await second.pending_steered_messages("s", "u", "b") == []
        for message_id in ("m1", "m2"):
            with pytest.raises(
                ValueError, match="another_agent|session_agent_mismatch"
            ):
                await second.submit_steered_message(
                    session_id="s",
                    user_id="u",
                    space_id="t",
                    agent_instance_id="b",
                    message_id=message_id,
                    content="first",
                )
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


def test_pending_opening_id_cannot_accompany_a_resume() -> None:
    from fred_runtime.app.agent_app import _AgentExecuteRequest

    with pytest.raises(ValueError, match="ordinary text turn"):
        _AgentExecuteRequest(
            agent_instance_id="a",
            message="first update",
            pending_message_id="m1",
            resume_payload={"approved": True},
        )
    with pytest.raises(ValueError, match="ordinary text turn"):
        _AgentExecuteRequest(
            agent_id="test.graph", message="first update", pending_message_id="m1"
        )


@pytest.mark.asyncio
async def test_submission_normalizes_nul_before_storage_and_retry(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        kwargs = dict(
            session_id="s",
            user_id="u",
            space_id="t",
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
        assert normalization is None
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_pending_updates_keep_the_conversations_canonical_space(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        await first.save(
            "s",
            [make_user_text("s", "ex", 0, "hello")],
            "u",
            space_id="project-a",
            agent_instance_id="a",
        )
        request = dict(
            session_id="s", user_id="u", agent_instance_id="a", content="update"
        )
        with pytest.raises(ValueError, match="session_space_mismatch"):
            await second.submit_steered_message(
                **request, space_id="project-b", message_id="m1"
            )
        row = await first.submit_steered_message(
            **request, space_id="project-a", message_id="m1"
        )
        with pytest.raises(ValueError, match="session_space_mismatch"):
            await second.submit_steered_message(
                **request, space_id="project-b", message_id="m1"
            )
        assert [
            item.rank for item in await second.pending_steered_messages("s", "u", "a")
        ] == [row.rank]
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
                space_id="t",
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
async def test_pending_burst_is_bounded_and_promoted_in_submission_order(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        for index in range(32):
            row = await first.submit_steered_message(
                session_id="s",
                user_id="u",
                space_id="t",
                agent_instance_id="a",
                message_id=f"m{index}",
                content=f"update {index}",
            )
            assert row.rank == -index - 1
        with pytest.raises(ValueError, match="too_many_pending_messages"):
            await second.submit_steered_message(
                session_id="s",
                user_id="u",
                space_id="t",
                agent_instance_id="a",
                message_id="m32",
                content="overflow",
            )
        pending = await second.pending_steered_messages("s", "u")
        assert [_text(row) for row in pending] == [
            f"update {index}" for index in range(32)
        ]
        for index in range(32):
            row = await second.deliver_steered_message(
                session_id="s",
                user_id="u",
                message_id=f"m{index}",
                rank=index + 1,
                exchange_id="ex",
                expected_content=f"update {index}",
            )
            assert row is not None and row.rank == index + 1
        assert await first.pending_steered_messages("s", "u") == []
        assert [row.rank for row in await first.get("s", "u")] == list(range(1, 33))
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_two_steers_after_tool_result_deliver_before_one_model_call(
    monkeypatch, tmp_path
):
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: queue.put_nowait)
    try:
        await first.save(
            "s",
            [
                make_user_text("s", "ex", 0, "Read the sources"),
                make_tool_call("s", "ex", 1, "c1", "lookup", {}),
                make_tool_result("s", "ex", 2, "c1", "Sources found"),
            ],
            "u",
        )
        for message_id, content in (
            ("m1", "Where are you?"),
            ("m2", "Read one more source"),
        ):
            await first.submit_steered_message(
                session_id="s",
                user_id="u",
                space_id="t",
                agent_instance_id="a",
                message_id=message_id,
                content=content,
            )
        wrong_agent = turn_steering.TurnSteeringMiddleware(
            "s", exchange_id="ex", agent_instance_id="b"
        )
        assert (
            await wrong_agent.abefore_model({"messages": []}, Runtime(context=None))
            is None
        )
        middleware = turn_steering.TurnSteeringMiddleware(
            "s", exchange_id="ex", agent_instance_id="a"
        )
        prior = [
            HumanMessage(content="Read the sources"),
            AIMessage(
                content="", tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}]
            ),
            ToolMessage(content="Sources found", tool_call_id="c1"),
        ]
        update = await middleware.abefore_model(
            {"messages": prior}, Runtime(context=None)
        )
        assert update is not None
        assert [message.id for message in update["messages"]] == [
            "steered:m1",
            "steered:m2",
        ]
        ranker = _HistoryRanker(
            3,
            opening_rank=0,
            pending_message_id=None,
            previously_pending_occurrence_ids=(),
        )
        delivered_events = []

        async def persist():
            for expected_id in ("m1", "m2"):
                event = await queue.get()
                assert event.message_id == expected_id
                delivered_events.append(
                    await _rank_runtime_event(
                        event.model_dump(mode="json"),
                        ranker,
                        session_id="s",
                        user_id="u",
                        exchange_id="ex",
                    )
                )

        calls = []

        async def handler(request):
            calls.append(request)
            assert [message.type for message in request.messages] == [
                "human",
                "ai",
                "tool",
                "human",
                "human",
            ]
            assert request.tools
            assert [
                row.rank
                for row in await first.get("s", "u")
                if row.role.value == "user"
            ] == [0, 3, 4]
            return ModelResponse(
                result=[AIMessage(content="Final answer covering both updates")]
            )

        with RunScope.open():
            consumer = asyncio.create_task(persist())
            response = await asyncio.wait_for(
                middleware.awrap_model_call(
                    ModelRequest(
                        model=cast(BaseChatModel, object()),
                        messages=[*prior, *update["messages"]],
                        tools=[cast(Any, object())],
                    ),
                    handler,
                ),
                5,
            )
            await consumer
        assert len(calls) == 1
        assert [event["rank"] for event in delivered_events] == [3, 4]
        assert response.result[0].content == "Final answer covering both updates"
        assert not any(
            row.role.value == "assistant" and row.channel.value == "final"
            for row in await first.get("s", "u")
        )
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_failed_delivery_keeps_message_pending_and_skips_model(
    monkeypatch, tmp_path
):
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: queue.put_nowait)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="Stop now",
        )
        middleware = turn_steering.TurnSteeringMiddleware(
            "s", exchange_id="ex", agent_instance_id="a"
        )
        update = await middleware.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None
        ranker = _HistoryRanker(
            1,
            opening_rank=0,
            pending_message_id=None,
            previously_pending_occurrence_ids=(),
        )
        called = False

        async def handler(_request):
            nonlocal called
            called = True
            return ModelResponse(result=[AIMessage(content="unexpected")])

        async def fail_persistence():
            event = await queue.get()
            with pytest.raises(ValueError, match="pending_message_content_mismatch"):
                await _rank_runtime_event(
                    event.model_copy(update={"content": "corrupted"}).model_dump(
                        mode="json"
                    ),
                    ranker,
                    session_id="s",
                    user_id="u",
                    exchange_id="ex",
                )

        with RunScope.open():
            consumer = asyncio.create_task(fail_persistence())
            with pytest.raises(ValueError, match="pending_message_content_mismatch"):
                await asyncio.wait_for(
                    middleware.awrap_model_call(
                        ModelRequest(
                            model=cast(BaseChatModel, object()),
                            messages=update["messages"],
                        ),
                        handler,
                    ),
                    5,
                )
            await consumer
        assert not called
        assert [
            _text(row) for row in await first.pending_steered_messages("s", "u")
        ] == ["Stop now"]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_another_exchange_cannot_promote_a_stale_pending_read(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="Change the task",
        )
        assert await first.pending_steered_messages("s", "u")
        assert await second.pending_steered_messages("s", "u")
        first_delivery = await first.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=0,
            exchange_id="winner",
        )
        assert first_delivery is not None and first_delivery.rank == 0
        with pytest.raises(ValueError, match="delivered_in_another_exchange"):
            await second.deliver_steered_message(
                session_id="s",
                user_id="u",
                message_id="m1",
                rank=1,
                exchange_id="loser",
            )
        retry = await second.deliver_steered_message(
            session_id="s",
            user_id="u",
            message_id="m1",
            rank=1,
            exchange_id="winner",
        )
        assert retry is not None and retry.rank == 0
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_opening_steer_uses_its_existing_rank(monkeypatch, tmp_path):
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: queue.put_nowait)
    try:
        await first.submit_steered_message(
            session_id="s",
            user_id="u",
            space_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="New turn",
        )
        middleware = turn_steering.TurnSteeringMiddleware(
            "s", pending_message_id="m1", exchange_id="ex", agent_instance_id="a"
        )
        assert (
            await middleware.abefore_model({"messages": []}, Runtime(context=None))
            is None
        )
        ranker = _HistoryRanker(
            1,
            opening_rank=0,
            pending_message_id="m1",
            previously_pending_occurrence_ids=(),
        )

        async def persist():
            event = await queue.get()
            return await _rank_runtime_event(
                event.model_dump(mode="json"),
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )

        async def handler(_request):
            return ModelResponse(result=[AIMessage(content="Answer")])

        with RunScope.open():
            consumer = asyncio.create_task(persist())
            await middleware.awrap_model_call(
                ModelRequest(
                    model=cast(BaseChatModel, object()),
                    messages=[HumanMessage(content="New turn")],
                ),
                handler,
            )
            payload = await consumer
        assert payload["rank"] == 0
        assert [row.rank for row in await first.get("s", "u")] == [0]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_kind", ["react", "deep"])
@pytest.mark.parametrize("timing", ["before_first_model", "during_tool"])
async def test_compiled_agent_applies_two_steers_without_interim_reply(
    monkeypatch, tmp_path, agent_kind: str, timing: str
) -> None:
    from types import SimpleNamespace

    from deepagents.backends import StateBackend
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event
    from fred_runtime.deep import deep_runtime
    from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
    from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
    from fred_sdk.contracts.context import (
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
    )
    from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
    from langchain_core.tools import tool

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    checkpointer = FredSqlCheckpointer(second_engine, prefix="v2_")
    await checkpointer._ensure_tables()
    checkpoint_waiting = asyncio.Event()
    release_checkpoint = asyncio.Event()
    if timing == "before_first_model":
        original_put = checkpointer.aput
        original_put_writes = checkpointer.aput_writes

        async def delayed_put(config, checkpoint, metadata, new_versions):
            messages = checkpoint.get("channel_values", {}).get("messages", [])
            if (
                agent_kind == "react"
                and not checkpoint_waiting.is_set()
                and any(
                    getattr(message, "id", None) == "steered:m1" for message in messages
                )
            ):
                checkpoint_waiting.set()
                await release_checkpoint.wait()
            return await original_put(config, checkpoint, metadata, new_versions)

        monkeypatch.setattr(checkpointer, "aput", delayed_put)

        async def delayed_put_writes(config, writes, task_id, task_path=""):
            if (
                agent_kind == "deep"
                and not checkpoint_waiting.is_set()
                and any(
                    channel == "messages"
                    and isinstance(value, list)
                    and any(
                        getattr(message, "id", None) == "steered:m1"
                        for message in value
                    )
                    for channel, value in writes
                )
            ):
                checkpoint_waiting.set()
                await release_checkpoint.wait()
            return await original_put_writes(config, writes, task_id, task_path)

        monkeypatch.setattr(checkpointer, "aput_writes", delayed_put_writes)
    events: asyncio.Queue[Any] = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.put_nowait)
    entered = asyncio.Event()
    release = asyncio.Event()

    @tool
    async def read_source(query: str) -> str:
        """Read a source in the test corpus."""
        entered.set()
        await release.wait()
        return f"Source for {query}"

    model = _ScriptedSteeringModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "read_source", "args": {"query": "first"}, "id": "call-1"}
                ],
            ),
            AIMessage(content="The final answer includes the extra sources."),
        ]
    )
    binding = local_binding(
        "test.steering",
        runtime_context=RuntimeContext(
            session_id="s", user_id="u", space_id="t", language="en"
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
            space_id="t",
            baggage={"steering_enabled": "true", "agent_instance_id": "a"},
        ),
    )
    if agent_kind == "react":
        graph = build_tool_loop_compiled_react_agent(
            model=model,
            tools=[read_source],
            system_prompt="Summarize the sources.",
            binding=binding,
            approval_policy=ToolApprovalPolicy(enabled=False),
            checkpointer=checkpointer,
            definition=cast(
                ReActAgentDefinition, SimpleNamespace(agent_id="test.steering")
            ),
            available_tool_names={"read_source"},
        )
    else:
        middleware = deep_runtime._build_deepagent_runtime_middleware(
            tracer=None,
            kpi=None,
            binding=binding,
            approval_policy=ToolApprovalPolicy(enabled=False),
            available_tool_names={"read_source"},
        )
        graph = deep_runtime._create_compiled_deep_agent(
            model=model,
            tools=[read_source],
            system_prompt="Summarize the sources.",
            checkpointer=checkpointer,
            subagent_middleware=[],
            middleware=middleware,
            backend=StateBackend(),
            permissions=[],
        )
    try:
        await first.save("s", [make_user_text("s", "ex", 0, "Summarize sources")], "u")

        async def submit_updates():
            for message_id, content in (
                ("m1", "Where are you?"),
                ("m2", "Include two more sources."),
            ):
                await first.submit_steered_message(
                    session_id="s",
                    user_id="u",
                    space_id="t",
                    agent_instance_id=INSTANCE_ID,
                    message_id=message_id,
                    content=content,
                )

        if timing == "before_first_model":
            await submit_updates()
        ranker = _HistoryRanker(
            1,
            opening_rank=0,
            pending_message_id=None,
            previously_pending_occurrence_ids=(),
        )
        delivered = []

        async def persist_updates():
            for expected_id in ("m1", "m2"):
                event = await events.get()
                assert event.message_id == expected_id
                checkpoint = await cast(Any, graph).aget_state(
                    {"configurable": {"thread_id": "s"}}
                )
                assert any(
                    message.id == f"steered:{expected_id}"
                    for message in checkpoint.values["messages"]
                )
                delivered.append(
                    await _rank_runtime_event(
                        event.model_dump(mode="json"),
                        ranker,
                        session_id="s",
                        user_id="u",
                        exchange_id="ex",
                    )
                )

        with active_turn(binding):
            consumer = asyncio.create_task(persist_updates())
            run = asyncio.create_task(
                cast(Any, graph).ainvoke(
                    {"messages": [HumanMessage(content="Summarize sources")]},
                    {"configurable": {"thread_id": "s"}},
                    durability="sync",
                )
            )
            if timing == "before_first_model":
                await asyncio.wait_for(checkpoint_waiting.wait(), 10)
                assert events.empty()
                release_checkpoint.set()
            await asyncio.wait_for(entered.wait(), 10)
            if timing == "during_tool":
                await submit_updates()
            release.set()
            state = await asyncio.wait_for(run, 15)
            await asyncio.wait_for(consumer, 5)
        assert [event["rank"] for event in delivered] == [1, 2]
        assert len(model.calls) == 2
        affected_call = model.calls[0 if timing == "before_first_model" else 1]
        assert [message.type for message in affected_call[-2:]] == ["human", "human"]
        assert (
            state["messages"][-1].content
            == "The final answer includes the extra sources."
        )
        assert [
            _text(row) for row in await first.get("s", "u") if row.role.value == "user"
        ] == [
            "Summarize sources",
            "Where are you?",
            "Include two more sources.",
        ]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()
