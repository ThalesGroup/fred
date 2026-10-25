import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.runtime_support import turn_steering
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages


def test_mailbox_rejects_mismatch_and_deduplicates_messages() -> None:
    mailbox = turn_steering.TurnSteeringMailbox()
    assert not mailbox.offer("s", "a", "u", "t", "m", "hello")
    token = mailbox.start("s", "a", "u", "t")
    assert token is not None
    assert mailbox.start("s", "a", "u", "t") is None
    assert not mailbox.offer("s", "other", "u", "t", "m", "hello")
    assert not mailbox.offer("s", "a", "other", "t", "m", "hello")
    assert not mailbox.offer("s", "a", "u", "other", "m", "hello")
    assert mailbox.offer("s", "a", "u", "t", "m", "hello")
    assert mailbox.offer("s", "a", "u", "t", "m", "hello")
    assert mailbox.take("s") == [("m", "hello")]
    assert mailbox.take("s") == []
    mailbox.end("s", token)
    assert not mailbox.offer("s", "a", "u", "t", "other", "later")


def test_human_pause_carries_undelivered_message_to_matching_resume(
    monkeypatch,
) -> None:
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    mailbox = turn_steering.TurnSteeringMailbox()
    monkeypatch.setattr(turn_steering, "turn_steering_mailbox", mailbox)
    token = mailbox.start("paused-session", "agent", "user", "team")
    assert token is not None
    assert mailbox.offer(
        "paused-session", "agent", "user", "team", "message", "focus on Marseille"
    )
    mailbox.end("paused-session", token, paused=True)

    assert not mailbox.offer(
        "paused-session", "agent", "user", "team", "other", "too late"
    )
    assert (
        mailbox.start("paused-session", "agent", "other", "team", resume=True) is None
    )
    resumed = mailbox.start("paused-session", "agent", "user", "team", resume=True)
    assert resumed is not None and resumed != token
    mailbox.end("paused-session", token)
    assert mailbox.offer(
        "paused-session", "agent", "user", "team", "message", "duplicate"
    )
    middleware = turn_steering.TurnSteeringMiddleware("paused-session")
    update = asyncio.run(middleware.abefore_model({}, None))
    assert update == {"messages": [HumanMessage(content="focus on Marseille")]}
    assert [(event.message_id, event.content) for event in events] == [
        ("message", "focus on Marseille")
    ]
    assert asyncio.run(middleware.abefore_model({}, None)) is None
    mailbox.end("paused-session", resumed)
    assert not mailbox.offer("paused-session", "agent", "user", "team", "later", "new")


def test_unrelated_turn_does_not_inherit_paused_message() -> None:
    mailbox = turn_steering.TurnSteeringMailbox()
    token = mailbox.start("session", "agent", "user", "team")
    assert token is not None
    assert mailbox.offer("session", "agent", "user", "team", "old", "do not inherit")
    mailbox.end("session", token, paused=True)

    next_token = mailbox.start("session", "agent", "user", "team")
    assert next_token is not None
    assert mailbox.take("session") == []
    mailbox.end("session", next_token)


def test_empty_human_pause_does_not_retain_mailbox() -> None:
    mailbox = turn_steering.TurnSteeringMailbox()
    token = mailbox.start("session", "agent", "user", "team")
    assert token is not None
    mailbox.end("session", token, paused=True)
    assert "session" not in mailbox._turns


def test_steering_enters_after_completed_tool_pair(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    token = turn_steering.turn_steering_mailbox.start("steer-test", "a", "u", "t")
    assert token is not None
    try:
        assert turn_steering.turn_steering_mailbox.offer(
            "steer-test", "a", "u", "t", "m", "new direction"
        )
        middleware = turn_steering.TurnSteeringMiddleware("steer-test")
        update = asyncio.run(middleware.abefore_model({}, None))
        assert update is not None
        history = [
            HumanMessage(content="original"),
            AIMessage(
                content="", tool_calls=[{"name": "search", "args": {}, "id": "call-1"}]
            ),
            ToolMessage(content="result", tool_call_id="call-1"),
        ]
        merged = add_messages(history, update["messages"])
        assert [type(item) for item in merged] == [
            HumanMessage,
            AIMessage,
            ToolMessage,
            HumanMessage,
        ]
        assert merged[-1].content == "new direction"
        assert [(event.message_id, event.content) for event in events] == [
            ("m", "new direction")
        ]
        assert asyncio.run(middleware.abefore_model({}, None)) is None
    finally:
        turn_steering.turn_steering_mailbox.end("steer-test", token)


def test_steering_route_authorizes_before_offering(monkeypatch, minimal_config) -> None:
    router = agent_app_module._build_agent_router(
        registry={}, security_enabled=True, max_chat_input_chars=5_000
    )
    endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.endpoint.__name__ == "steer_active_turn"
    )
    checked = []

    async def check_owner(*args, **kwargs) -> None:
        checked.append("owner")

    async def check_execution(*args, **kwargs) -> None:
        checked.append("execution")

    monkeypatch.setattr(agent_app_module, "_enforce_session_ownership", check_owner)
    monkeypatch.setattr(
        agent_app_module, "_authorize_execution_or_raise", check_execution
    )
    request = RuntimeExecuteRequest.model_validate(
        {
            "input": "new direction",
            "session_id": "route-steer",
            "agent_instance_id": "agent",
            "runtime_context": {"team_id": "team"},
        }
    )
    args = {
        "session_id": "route-steer",
        "request": request,
        "message_id": "message",
        "authenticated_user": SimpleNamespace(uid="user"),
        "container": PodApplicationContext(minimal_config),
    }
    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(endpoint(**args))
    assert unavailable.value.status_code == 409
    assert checked == ["owner", "execution"]

    token = turn_steering.turn_steering_mailbox.start(
        "route-steer", "agent", "user", "team"
    )
    assert token is not None
    try:
        assert asyncio.run(endpoint(**args)) == {"status": "pending"}
        assert turn_steering.turn_steering_mailbox.take("route-steer") == [
            ("message", "new direction")
        ]
    finally:
        turn_steering.turn_steering_mailbox.end("route-steer", token)
