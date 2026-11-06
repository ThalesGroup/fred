"""History-backed in-thread user messages across runtime replicas."""

import asyncio
from typing import Any, cast

import fred_runtime.deep.deep_runtime as deep_runtime
import pytest
from deepagents.backends import StateBackend
from fred_core.history.history_schema import (
    ChatMessage,
    TextPart,
    make_assistant_final,
    make_tool_call,
    make_tool_result,
    make_user_text,
)
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
from fred_runtime.support.reasoning_replay import with_mistral_reasoning_replay
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    ReActAgentDefinition,
    ToolApprovalPolicy,
)
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableBinding
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from pydantic import Field, SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent


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


@pytest.mark.parametrize("terminal_kind", ["awaiting_human", "final"])
def test_graph_fallback_acknowledges_at_terminal_boundary_once(terminal_kind):
    from fred_runtime.app.agent_app import _AgentExecuteRequest, _TurnEventExpander

    expander = _TurnEventExpander(
        _UnusedGraph(),
        _AgentExecuteRequest(
            agent_id="test.graph", message="new turn", pending_message_id="m1"
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
async def test_pending_burst_is_bounded_and_promoted_in_submission_order(tmp_path):
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        for index in range(32):
            row = await first.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id=f"m{index}",
                content=f"update {index}",
            )
            assert row.rank == -index - 1
        with pytest.raises(ValueError, match="too_many_pending_messages"):
            await second.submit_steered_message(
                session_id="s",
                user_id="u",
                team_id="t",
                agent_instance_id="a",
                message_id="m32",
                content="overflow",
            )
        pending = await second.pending_steered_messages("s", "u")
        assert [_text(row) for row in pending] == [
            f"update {index}" for index in range(32)
        ]
        delivered, reply = await second.persist_steered_assistant_message(
            session_id="s",
            user_id="u",
            exchange_id="ex",
            rank=33,
            message_ids=tuple(f"m{index}" for index in range(32)),
            content="I received all 32 updates.",
            deliveries=tuple(
                (f"m{index}", f"update {index}", index + 1) for index in range(32)
            ),
        )
        assert [row.rank for row in delivered] == list(range(1, 33))
        assert reply.rank == 33
        assert await first.pending_steered_messages("s", "u") == []
        assert [row.rank for row in await first.get("s", "u")] == list(range(1, 34))
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
        assert request.messages[-2].content == "I am checking the sources."
        assert isinstance(request.messages[-1], HumanMessage)
        assert "complete any question or request" in request.messages[-1].content
        assert "later updates can revise earlier ones" in request.messages[-1].content
        assert "If the task remains stopped" in request.messages[-1].content
        assert [message.type for message in request.messages] == [
            "human",
            "ai",
            "tool",
            "human",
            "ai",
            "human",
        ]
        return ModelResponse(result=[AIMessage(content="Continuing work.")])

    with RunScope.open() as scope:
        scope_holder.append(scope)
        response = await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[
                    HumanMessage(content="Original task"),
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}],
                    ),
                    ToolMessage(content="Source found", tool_call_id="call-1"),
                    HumanMessage(content="Where are you?"),
                ],
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
async def test_recovered_steered_reply_continues_with_user_last():
    middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
    prior_reply = AIMessage(
        id=steered_reply_id(("m1",)),
        content="I am checking the sources.",
        additional_kwargs={"steered_reply_for": ["m1"]},
    )
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.messages[-2] is prior_reply
        assert isinstance(request.messages[-1], HumanMessage)
        return ModelResponse(result=[AIMessage(content="Continuing work.")])

    response = await middleware.awrap_model_call(
        ModelRequest(
            model=cast(BaseChatModel, object()),
            messages=[HumanMessage(content="Where are you?"), prior_reply],
        ),
        handler,
    )
    assert len(calls) == 1
    assert [message.content for message in response.result] == ["Continuing work."]


@pytest.mark.parametrize("model_name", ["mistral-medium-latest", "gpt-6-luna"])
def test_steered_continuation_serializes_for_provider(model_name):
    model = cast(
        ChatOpenAI,
        with_mistral_reasoning_replay(
            ChatOpenAI(model=model_name, api_key=SecretStr("test-key"))
        ),
    )
    reply = AIMessage(
        content="I am checking the sources.",
        additional_kwargs={"steered_reply_for": ["m1"]},
    )
    request = ModelRequest(
        model=model,
        messages=[HumanMessage(content="Where are you?"), reply],
    )
    continued = turn_steering._continue_after_steered_reply(request)
    wire = model._get_request_payload(continued.messages)["messages"]
    assert [message["role"] for message in wire] == ["user", "assistant", "user"]


@pytest.mark.parametrize("model_name", ["mistral-medium-latest", "gpt-6-luna"])
@pytest.mark.parametrize("with_tools", [False, True])
def test_visible_reply_disables_openai_compatible_reasoning_only_for_interim(
    model_name: str, with_tools: bool
) -> None:
    @tool
    def read_document(uid: str) -> str:
        """Read one document."""
        return uid

    model = ChatOpenAI.model_validate(
        {
            "model": model_name,
            "api_key": "offline-test",
            "reasoning_effort": "high",
            **(
                {"base_url": "https://api.mistral.ai/v1"}
                if model_name.startswith("mistral")
                else {}
            ),
        }
    )
    if model_name.startswith("mistral"):
        model = cast(ChatOpenAI, with_mistral_reasoning_replay(model))
    prior = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Private reasoning"},
            {"type": "text", "text": "One document read."},
        ],
        tool_calls=[
            {"name": "read_document", "args": {"uid": "tool-args"}, "id": "call1"}
        ],
    )
    messages = [
        HumanMessage(content="Read the documents."),
        prior,
        ToolMessage(
            content="Found one title.", tool_call_id="call1", name="read_document"
        ),
        HumanMessage(content="Where are you?"),
    ]
    request = ModelRequest(
        model=model,
        messages=messages,
        model_settings={"reasoning_effort": "high"},
        tools=[read_document] if with_tools else [],
    )
    interim = turn_steering._visible_reply_request(
        request, SystemMessage(content="Answer the update briefly.")
    )
    interim_model = cast(ChatOpenAI, interim.model)

    assert type(interim_model) is type(model)
    assert interim_model is not model
    assert interim_model.client is model.client
    assert interim_model.async_client is model.async_client
    assert interim_model.reasoning_effort is None
    assert "reasoning_effort" not in interim.model_settings
    assert interim.tool_choice == "none"
    assert interim.tools == request.tools
    if with_tools:
        assert "tool_choice" not in interim.model_settings
        bound = interim_model.bind_tools(
            interim.tools, tool_choice=interim.tool_choice, **interim.model_settings
        )
        assert isinstance(bound, RunnableBinding)
        payload_settings = bound.kwargs
    else:
        assert interim.model_settings["tool_choice"] == "none"
        payload_settings = interim.model_settings
    interim_payload = interim_model._get_request_payload(
        interim.messages, **payload_settings
    )
    assert "reasoning_effort" not in interim_payload
    assert interim_payload["tool_choice"] == "none"
    if "messages" in interim_payload:
        wire_messages = interim_payload["messages"]
        assert [message["role"] for message in wire_messages] == [
            "user",
            "assistant",
            "tool",
            "user",
        ]
        assert wire_messages[1]["content"] == "One document read."
        assert wire_messages[2]["content"] == "Found one title."
    else:
        wire_items = interim_payload["input"]
        assert [item["type"] for item in wire_items] == [
            "message",
            "message",
            "function_call",
            "function_call_output",
            "message",
        ]
        assert "One document read." in str(wire_items[1]["content"])
        assert wire_items[3]["output"] == "Found one title."
    assert isinstance(prior.content, list)
    assert model._get_request_payload(messages)["reasoning_effort"] == "high"
    assert request.model is model
    assert request.model_settings == {"reasoning_effort": "high"}


def test_visible_reply_preserves_explicitly_disabled_reasoning() -> None:
    @tool
    def read_document(uid: str) -> str:
        """Read one document."""
        return uid

    model = ChatOpenAI.model_validate(
        {
            "model": "gpt-6-luna",
            "api_key": "offline-test",
            "reasoning_effort": "none",
            "use_responses_api": False,
        }
    )
    request = ModelRequest(
        model=model,
        messages=[HumanMessage(content="Where are you?")],
        tools=[read_document],
    )

    interim = turn_steering._visible_reply_request(
        request, SystemMessage(content="Answer briefly.")
    )
    interim_model = cast(ChatOpenAI, interim.model)
    bound = interim_model.bind_tools(
        interim.tools, tool_choice=interim.tool_choice, **interim.model_settings
    )
    assert isinstance(bound, RunnableBinding)
    payload = interim_model._get_request_payload(interim.messages, **bound.kwargs)

    assert payload["reasoning_effort"] == "none"
    assert payload["tool_choice"] == "none"
    assert model.reasoning_effort == "none"


def test_visible_reply_uses_provider_neutral_tool_suppression() -> None:
    @tool
    def read_document(uid: str) -> str:
        """Read one document."""
        return uid

    model = ChatAnthropic.model_validate(
        {"model": "claude-sonnet-4-5", "api_key": "offline-test"}
    )
    messages: list[AnyMessage] = [
        HumanMessage(content="Read the documents."),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "read_document", "args": {"uid": "one"}, "id": "call1"}
            ],
        ),
        ToolMessage(content="Found one title.", tool_call_id="call1"),
        HumanMessage(content="Where are you?"),
    ]
    request = ModelRequest(model=model, messages=messages, tools=[read_document])

    interim = turn_steering._visible_reply_request(
        request, SystemMessage(content="Answer the update briefly.")
    )

    assert interim.model is model
    assert interim.messages is messages
    assert interim.tools == []
    assert interim.tool_choice is None
    assert request.tools == [read_document]
    assert request.tool_choice is None
    payload = model._get_request_payload(interim.messages)
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "user",
    ]
    assert payload["messages"][1]["content"][0]["type"] == "tool_use"
    assert payload["messages"][2]["content"][0]["type"] == "tool_result"


@pytest.mark.asyncio
async def test_failed_steered_reply_does_not_emit_delivery(monkeypatch):
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
    middleware._unanswered_ids = ("m1",)
    middleware._pending_delivery = (("m1", "Where are you?"),)

    async def unavailable_reply(_request):
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[HumanMessage(content="Where are you?")],
            ),
            unavailable_reply,
        )
    assert events == [{"kind": "_steered_reply_start"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_kind",
    [
        "empty",
        "reasoning",
        "tool",
        "missing",
        "structured",
        "embedded_structured",
        "fenced_structured",
        "long",
    ],
)
async def test_invalid_interim_reply_falls_back_and_continues(
    monkeypatch, invalid_kind
):
    events = []
    scope_holder = []

    def write(event):
        events.append(event)
        if getattr(event, "kind", None) == "steered_assistant_message":
            scope_holder[0].complete_event_receipt(
                steered_reply_id(("m1", "m2")), {"content": event.content}
            )

    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: write)
    middleware = turn_steering.TurnSteeringMiddleware(
        "s", exchange_id="ex", language="fr" if invalid_kind == "reasoning" else None
    )
    middleware._unanswered_ids = ("m1", "m2")
    middleware._pending_delivery = (("m1", "Status?"), ("m2", "Add two docs"))
    if invalid_kind == "reasoning":
        invalid = ModelResponse(
            result=[AIMessage(content=[{"type": "thinking", "thinking": "planning"}])]
        )
    elif invalid_kind == "tool":
        invalid = ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}],
                )
            ]
        )
    elif invalid_kind == "missing":
        invalid = ModelResponse(result=[])
    elif invalid_kind == "structured":
        invalid = ModelResponse(
            result=[AIMessage(content='{"document_uid": "doc-1", "max_chars": 500}')]
        )
    elif invalid_kind == "embedded_structured":
        invalid = ModelResponse(
            result=[AIMessage(content='I will ask. {"question": "Which one?"}')]
        )
    elif invalid_kind == "fenced_structured":
        invalid = ModelResponse(
            result=[AIMessage(content='```json\n{"document_uid": "doc-1"}\n```')]
        )
    elif invalid_kind == "long":
        invalid = ModelResponse(result=[AIMessage(content="A long answer. " * 50)])
    else:
        invalid = ModelResponse(result=[AIMessage(content="")])
    for message in invalid.result:
        if isinstance(message, AIMessage):
            message.usage_metadata = {
                "input_tokens": 12,
                "output_tokens": 5,
                "total_tokens": 17,
            }
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) <= 2:
            assert request.tools == []
            assert request.tool_choice is None
            return invalid
        assert isinstance(request.messages[-1], HumanMessage)
        return ModelResponse(result=[AIMessage(content="Original task continues.")])

    with RunScope.open() as scope:
        scope_holder.append(scope)
        response = await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[HumanMessage(content="Add two docs")],
            ),
            handler,
        )
    assert len(calls) == 3
    assert len(events) == 2
    assert events[1].message_ids == ("m1", "m2")
    assert [item.message_id for item in events[1].deliveries] == ["m1", "m2"]
    assert events[1].content == (
        "Je n'ai pas pu répondre immédiatement à tes messages. Je les ai pris en compte."
        if invalid_kind == "reasoning"
        else "I could not answer your updates immediately. I have taken them into account."
    )
    assert [message.content for message in response.result] == [
        events[1].content,
        "Original task continues.",
    ]
    assert isinstance(response.result[0], AIMessage)
    assert response.result[0].usage_metadata == (
        None
        if invalid_kind == "missing"
        else {
            "input_tokens": 24,
            "output_tokens": 10,
            "total_tokens": 34,
            "input_token_details": {"cache_read": 0, "cache_creation": 0},
        }
    )


def test_visible_reply_accepts_bracketed_document_references() -> None:
    text = "Je prends les documents [1, 2] en compte."
    assert turn_steering._visible_reply_text(AIMessage(content=text)) == (text, "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_reply", ["", '{"document_uid": "doc-1", "max_chars": 500}']
)
async def test_valid_retry_replies_without_fallback(monkeypatch, first_reply):
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
    middleware._pending_delivery = (("m1", "Status?"),)
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return ModelResponse(
                result=[
                    AIMessage(
                        content=first_reply,
                        usage_metadata={
                            "input_tokens": 12,
                            "output_tokens": 5,
                            "total_tokens": 17,
                        },
                    )
                ]
            )
        if len(calls) == 2:
            return ModelResponse(
                result=[
                    AIMessage(
                        content="I am checking the sources.",
                        usage_metadata={
                            "input_tokens": 14,
                            "output_tokens": 6,
                            "total_tokens": 20,
                        },
                    )
                ]
            )
        assert isinstance(request.messages[-1], HumanMessage)
        return ModelResponse(result=[AIMessage(content="Continuing work.")])

    with RunScope.open() as scope:
        scope_holder.append(scope)
        response = await middleware.awrap_model_call(
            ModelRequest(
                model=cast(BaseChatModel, object()),
                messages=[HumanMessage(content="Status?")],
            ),
            handler,
        )
    assert len(calls) == 3
    assert events[1].content == "I am checking the sources."
    assert isinstance(response.result[0], AIMessage)
    assert response.result[0].usage_metadata == {
        "input_tokens": 26,
        "output_tokens": 11,
        "total_tokens": 37,
        "input_token_details": {"cache_read": 0, "cache_creation": 0},
    }


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
                return ModelResponse(
                    result=[
                        AIMessage(
                            content="Checking.",
                            usage_metadata={
                                "input_tokens": 12,
                                "output_tokens": 3,
                                "total_tokens": 15,
                            },
                        )
                    ]
                )
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
        assert persisted_event["token_usage"]["total_tokens"] == 15
        assert [item.content for item in response.result] == ["Checking.", "Done."]
        persisted_reply = (await first.get("s", "u"))[1]
        assert persisted_reply.metadata.token_usage is None
        recovered = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        replay = await recovered.abefore_model({"messages": []}, Runtime(context=None))
        assert replay is not None
        assert replay["messages"][1].usage_metadata["total_tokens"] == 15
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_two_steers_during_tool_call_continue_one_turn(monkeypatch, tmp_path):
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
    queue = asyncio.Queue()
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: queue.put_nowait)
    try:
        await first.save(
            "s",
            [
                make_user_text("s", "ex", 0, "Read the sources and summarize them"),
                make_tool_call("s", "ex", 1, "call-1", "lookup", {}),
            ],
            "u",
        )
        tool_started = asyncio.Event()
        release_tool = asyncio.Event()

        async def running_tool():
            tool_started.set()
            await release_tool.wait()
            return "Sources found"

        tool_task = asyncio.create_task(running_tool())
        await tool_started.wait()
        first_steer = await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m1",
            content="Where are you?",
        )
        second_steer = await first.submit_steered_message(
            session_id="s",
            user_id="u",
            team_id="t",
            agent_instance_id="a",
            message_id="m2",
            content="Also include two more documents",
        )
        assert (first_steer.rank, second_steer.rank) == (-1, -2)
        release_tool.set()
        tool_result = await tool_task
        await first.save(
            "s", [make_tool_result("s", "ex", 2, "call-1", tool_result)], "u"
        )
        prior_messages = [
            HumanMessage(content="Read the sources and summarize them"),
            AIMessage(
                content="",
                tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}],
            ),
            ToolMessage(content=tool_result, tool_call_id="call-1"),
        ]
        middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        update = await middleware.abefore_model(
            {"messages": prior_messages}, Runtime(context=None)
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

        async def persist_reply():
            assert await queue.get() == {"kind": "_steered_reply_start"}
            event = await queue.get()
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
                assert [message.type for message in request.messages] == [
                    "human",
                    "ai",
                    "tool",
                    "human",
                    "human",
                ]
                return ModelResponse(
                    result=[
                        AIMessage(
                            content="The lookup finished. I will include the two extra documents."
                        )
                    ]
                )
            assert [message.type for message in request.messages] == [
                "human",
                "ai",
                "tool",
                "human",
                "human",
                "ai",
                "human",
            ]
            return ModelResponse(
                result=[AIMessage(content="Summary with extra documents")]
            )

        with RunScope.open():
            consumer = asyncio.create_task(persist_reply())
            response = await asyncio.wait_for(
                middleware.awrap_model_call(
                    ModelRequest(
                        model=cast(BaseChatModel, object()),
                        messages=[*prior_messages, *update["messages"]],
                    ),
                    handler,
                ),
                timeout=5,
            )
            persisted_event = await consumer
        assert len(calls) == 2
        assert [item["rank"] for item in persisted_event["deliveries"]] == [3, 4]
        assert persisted_event["rank"] == 5
        final = await _rank_runtime_event(
            {"kind": "final", "content": response.result[-1].content},
            ranker,
            session_id="s",
            user_id="u",
            exchange_id="ex",
        )
        assert final["rank"] == 6
        await first.save(
            "s", [make_assistant_final("s", "ex", 6, final["content"])], "u"
        )
        rows = await first.get("s", "u")
        assert [(row.rank, row.channel.value) for row in rows] == [
            (0, "final"),
            (1, "tool_call"),
            (2, "tool_result"),
            (3, "final"),
            (4, "final"),
            (5, "final"),
            (6, "final"),
        ]
        assert [_text(row) for row in rows if row.role.value == "user"] == [
            "Read the sources and summarize them",
            "Where are you?",
            "Also include two more documents",
        ]
    finally:
        turn_steering.turn_messages.configure(None)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_kind", ["react", "deep"])
@pytest.mark.parametrize("timing", ["before_first_model", "during_tool"])
async def test_compiled_agent_handles_two_steers(
    monkeypatch, tmp_path, agent_kind: str, timing: str
) -> None:
    from types import SimpleNamespace

    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event

    first, second, first_engine, second_engine = await _replicas(tmp_path)
    turn_steering.turn_messages.configure(second)
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

    tool_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "read_source", "args": {"query": "first"}, "id": "call-1"}
        ],
    )
    interim = AIMessage(content="I will include the additional sources.")
    final = AIMessage(content="The summary includes all requested sources.")
    model = _ScriptedSteeringModel(
        script=[interim, tool_call, final]
        if timing == "before_first_model"
        else [tool_call, interim, final]
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s", user_id="u", team_id="t", language="en"
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
            team_id="t",
            baggage={"steering_enabled": "true"},
        ),
    )
    graph: Any
    if agent_kind == "react":
        graph = build_tool_loop_compiled_react_agent(
            model=model,
            tools=[read_source],
            system_prompt="Summarize the sources.",
            binding=binding,
            approval_policy=ToolApprovalPolicy(enabled=False),
            checkpointer=InMemorySaver(),
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
            checkpointer=InMemorySaver(),
            subagent_middleware=[],
            middleware=middleware,
            backend=StateBackend(),
            permissions=[],
        )
    try:
        await first.save("s", [make_user_text("s", "ex", 0, "Summarize sources")], "u")
        if timing == "before_first_model":
            for message_id, content in (
                ("m1", "Where are you?"),
                ("m2", "Include two more sources."),
            ):
                await first.submit_steered_message(
                    session_id="s",
                    user_id="u",
                    team_id="t",
                    agent_instance_id="a",
                    message_id=message_id,
                    content=content,
                )
        ranker = _HistoryRanker(
            1,
            opening_rank=0,
            pending_message_id=None,
            previously_pending_occurrence_ids=(),
        )

        async def persist_reply() -> dict[str, Any]:
            assert await events.get() == {"kind": "_steered_reply_start"}
            event = await events.get()
            return await _rank_runtime_event(
                event.model_dump(mode="json"),
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )

        with RunScope.open():
            consumer = asyncio.create_task(persist_reply())
            run = asyncio.create_task(
                graph.ainvoke(
                    {"messages": [HumanMessage(content="Summarize sources")]},
                    {"configurable": {"thread_id": "s"}},
                )
            )
            await asyncio.wait_for(entered.wait(), 10)
            if timing == "during_tool":
                for message_id, content in (
                    ("m1", "Where are you?"),
                    ("m2", "Include two more sources."),
                ):
                    await first.submit_steered_message(
                        session_id="s",
                        user_id="u",
                        team_id="t",
                        agent_instance_id="a",
                        message_id=message_id,
                        content=content,
                    )
            release.set()
            state = await asyncio.wait_for(run, 15)
            reply_event = await asyncio.wait_for(consumer, 5)

        assert [item["rank"] for item in reply_event["deliveries"]] == [1, 2]
        assert reply_event["rank"] == 3
        assert [
            message.content
            for message in state["messages"]
            if isinstance(message, ToolMessage)
        ] == ["Source for first"]
        assert (
            state["messages"][-1].content
            == "The summary includes all requested sources."
        )
        assert len(model.calls) == 3
        interim_index = 0 if timing == "before_first_model" else 1
        assert [message.type for message in model.calls[interim_index][-2:]] == [
            "human",
            "human",
        ]
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


@pytest.mark.asyncio
async def test_second_steer_arriving_during_reply_reaches_next_model_boundary(
    monkeypatch, tmp_path
):
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
            content="Where are you?",
        )
        middleware = turn_steering.TurnSteeringMiddleware("s", exchange_id="ex")
        first_update = await middleware.abefore_model(
            {"messages": []}, Runtime(context=None)
        )
        assert first_update is not None
        ranker = _HistoryRanker(
            1,
            opening_rank=0,
            pending_message_id=None,
            previously_pending_occurrence_ids=(),
        )

        async def persist_replies():
            for expected_id in ("m1", "m2"):
                assert await queue.get() == {"kind": "_steered_reply_start"}
                event = await queue.get()
                assert event.message_ids == (expected_id,)
                await _rank_runtime_event(
                    event.model_dump(mode="json"),
                    ranker,
                    session_id="s",
                    user_id="u",
                    exchange_id="ex",
                )

        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                await first.submit_steered_message(
                    session_id="s",
                    user_id="u",
                    team_id="t",
                    agent_instance_id="a",
                    message_id="m2",
                    content="Also inspect one more document",
                )
                return ModelResponse(
                    result=[AIMessage(content="The first lookup finished.")]
                )
            if calls == 2:
                assert request.tools != []
                return ModelResponse(
                    result=[
                        AIMessage(
                            content="",
                            tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}],
                        )
                    ]
                )
            if calls == 3:
                assert request.tools == []
                return ModelResponse(result=[AIMessage(content="I will inspect it.")])
            return ModelResponse(result=[AIMessage(content="Final answer.")])

        with RunScope.open():
            consumer = asyncio.create_task(persist_replies())
            first_response = await middleware.awrap_model_call(
                ModelRequest(
                    model=cast(BaseChatModel, object()),
                    messages=first_update["messages"],
                    tools=[cast(Any, object())],
                ),
                handler,
            )
            assert first_response.result[0].content == "The first lookup finished."
            first_output = cast(list[AIMessage], first_response.result)
            assert first_output[1].tool_calls[0]["id"] == "c1"
            tool_call = await _rank_runtime_event(
                {"kind": "tool_call", "call_id": "c1", "tool_name": "lookup"},
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )
            tool_result = await _rank_runtime_event(
                {"kind": "tool_result", "call_id": "c1", "content": "Found"},
                ranker,
                session_id="s",
                user_id="u",
                exchange_id="ex",
            )
            await first.save(
                "s",
                [
                    make_tool_call("s", "ex", tool_call["rank"], "c1", "lookup", {}),
                    make_tool_result("s", "ex", tool_result["rank"], "c1", "Found"),
                ],
                "u",
            )
            second_update = await middleware.abefore_model(
                {
                    "messages": [
                        *first_update["messages"],
                        *first_output,
                        ToolMessage(content="Found", tool_call_id="c1"),
                    ]
                },
                Runtime(context=None),
            )
            assert second_update is not None
            assert [message.id for message in second_update["messages"]] == [
                "steered:m2"
            ]
            second_response = await middleware.awrap_model_call(
                ModelRequest(
                    model=cast(BaseChatModel, object()),
                    messages=[
                        *first_update["messages"],
                        *first_output,
                        ToolMessage(content="Found", tool_call_id="c1"),
                        *second_update["messages"],
                    ],
                    tools=[cast(Any, object())],
                ),
                handler,
            )
            await consumer
        assert calls == 4
        assert [message.content for message in second_response.result] == [
            "I will inspect it.",
            "Final answer.",
        ]
        rows = await first.get("s", "u")
        assert [row.rank for row in rows] == [1, 2, 3, 4, 5, 6]
        assert [
            (row.rank, _text(row)) for row in rows if row.channel.value == "final"
        ] == [
            (1, "Where are you?"),
            (2, "The first lookup finished."),
            (5, "Also inspect one more document"),
            (6, "I will inspect it."),
        ]
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
