import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.runtime_support import turn_steering
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import ReActAgentDefinition
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine


async def _replicas(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'steering.sqlite'}"
    first_engine = create_async_engine(url)
    second_engine = create_async_engine(url)
    async with first_engine.begin() as conn:
        await conn.run_sync(turn_steering._metadata.create_all)
    return (
        turn_steering.TurnSteeringMailbox(first_engine),
        turn_steering.TurnSteeringMailbox(second_engine),
        first_engine,
        second_engine,
    )


@pytest.mark.asyncio
async def test_other_replica_offers_once_and_stale_turn_is_rejected(tmp_path) -> None:
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        assert not await second.offer("s", "a", "u", "t", "turn-1", "m", "hello")
        assert await first.start("s", "a", "u", "t", "turn-1") == "turn-1"
        assert await first.start("s", "a", "u", "t", "turn-2") is None
        assert not await second.offer("s", "other", "u", "t", "turn-1", "m", "hello")
        assert not await second.offer("s", "a", "other", "t", "turn-1", "m", "hello")
        assert not await second.offer("s", "a", "u", "other", "turn-1", "m", "hello")
        assert await second.offer("s", "a", "u", "t", "turn-1", "m", "hello")
        assert await second.offer("s", "a", "u", "t", "turn-1", "m", "duplicate")
        assert await first.take("s", "turn-1") == [("m", "hello")]
        assert await second.take("s", "turn-1") == []
        await first.end("s", "turn-1")
        assert await second.start("s", "a", "u", "t", "turn-2") == "turn-2"
        assert not await first.offer("s", "a", "u", "t", "turn-1", "late", "wrong turn")
        await second.end("s", "turn-2")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_human_pause_resumes_on_another_replica(monkeypatch, tmp_path) -> None:
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    monkeypatch.setattr(turn_steering, "turn_steering_mailbox", second)
    try:
        assert await first.start("s", "agent", "user", "team", "turn-1")
        assert await second.offer(
            "s", "agent", "user", "team", "turn-1", "message", "focus on Marseille"
        )
        await first.pause("s", "turn-1")
        await first.end("s", "turn-1", paused=True)
        assert not await first.offer(
            "s", "agent", "user", "team", "turn-1", "late", "too late"
        )
        assert (
            await second.start("s", "agent", "other", "team", "turn-2", resume=True)
            is None
        )
        assert await second.start("s", "agent", "user", "team", "turn-2", resume=True)
        await first.end("s", "turn-1")
        assert await first.offer(
            "s", "agent", "user", "team", "turn-2", "message", "duplicate"
        )
        middleware = turn_steering.TurnSteeringMiddleware("s", "turn-2")
        update = await middleware.abefore_model({"messages": []}, Runtime(context=None))
        assert update == {"messages": [HumanMessage(content="focus on Marseille")]}
        assert [(event.message_id, event.content) for event in events] == [
            ("message", "focus on Marseille")
        ]
        assert (
            await middleware.abefore_model({"messages": []}, Runtime(context=None))
            is None
        )
        await second.end("s", "turn-2")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_resume_takes_pending_before_old_stream_closes(tmp_path) -> None:
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        assert await first.start("s", "agent", "user", "team", "old")
        assert await second.offer("s", "agent", "user", "team", "old", "m", "pending")
        await first.pause("s", "old")
        assert await second.start("s", "agent", "user", "team", "new", resume=True)
        assert (
            await first.start("s", "agent", "user", "team", "competing", resume=True)
            is None
        )
        await first.end("s", "old", paused=True)
        assert await second.take("s", "new") == [("m", "pending")]
        assert await first.offer(
            "s", "agent", "user", "team", "new", "m2", "second pause"
        )
        await second.pause("s", "new")
        assert await first.start("s", "agent", "user", "team", "third", resume=True)
        await second.end("s", "new", paused=True)
        assert await first.take("s", "third") == [("m2", "second pause")]
        await first.end("s", "third")
        await second.end("s", "new")
        assert await first.start("fresh", "agent", "user", "team", "one", resume=True)
        assert (
            await second.start("fresh", "agent", "user", "team", "two", resume=True)
            is None
        )
        await first.end("fresh", "one")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_stream_marks_pause_before_emitting_human_event(
    monkeypatch, tmp_path
) -> None:
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", first)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(history_store=None)),
    )

    async def exchange_id(**kwargs):
        return "exchange"

    async def events(*args, **kwargs):
        assert await second.offer("s", "agent", "user", "space", "old", "m", "pending")
        yield {"kind": "awaiting_human"}

    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", exchange_id)
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", events)
    stream = agent_app_module._stream(
        cast(ReActAgentDefinition, SimpleNamespace(agent_id="agent")),
        agent_app_module._AgentExecuteRequest(
            agent_instance_id="agent",
            message="hello",
            context={"session_id": "s", "user_id": "user", "space_id": "space"},
            steering_turn_id="old",
        ),
        team_id="team",
        container=cast(PodApplicationContext, SimpleNamespace()),
    )
    try:
        assert "awaiting_human" in await anext(stream)
        assert await second.start("s", "agent", "user", "space", "new", resume=True)
        await stream.aclose()
        assert await second.take("s", "new") == [("m", "pending")]
    finally:
        await stream.aclose()
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_expired_owner_and_unrelated_resume_cannot_move_messages(
    tmp_path,
) -> None:
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    try:
        assert await first.start("s", "agent", "user", "team", "old")
        assert await second.offer("s", "agent", "user", "team", "old", "m", "pending")
        await first.pause("s", "old")
        await first.end("s", "old", paused=True)
        assert await second.start("s", "agent", "user", "team", "new") == "new"
        assert await first.take("s", "old") == []
        assert await second.take("s", "new") == []
        await first.end("s", "old")
        assert await second.offer("s", "agent", "user", "team", "new", "m2", "current")
        async with first_engine.begin() as conn:
            await conn.execute(
                update(turn_steering._turns)
                .where(turn_steering._turns.c.session_id == "s")
                .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )
        assert not await first.offer("s", "agent", "user", "team", "new", "m3", "late")
        await first.cleanup_expired()
        assert await second.take("s", "new") == []
        assert await first.start("s", "agent", "user", "team", "replacement")
        assert await second.take("s", "replacement") == []
        await second.end("s", "replacement")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_runtime_without_sql_keeps_ordinary_turn_available() -> None:
    mailbox = turn_steering.TurnSteeringMailbox()
    assert await mailbox.start("s", "a", "u", "t", "turn") is None
    assert not await mailbox.offer("s", "a", "u", "t", "turn", "m", "hello")
    await mailbox.purge("s", "u")
    await mailbox.cleanup_expired()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_postgres_replicas_consume_concurrent_offers_once() -> None:
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    first_engine = create_async_engine(url)
    second_engine = create_async_engine(url)
    first = turn_steering.TurnSteeringMailbox(first_engine)
    second = turn_steering.TurnSteeringMailbox(second_engine)
    session_id = f"{uuid4().hex}{'s' * 170}"
    agent_id, user_id, team_id = "a" * 200, "u" * 200, "t" * 200
    try:
        async with first_engine.begin() as conn:
            await conn.run_sync(turn_steering._metadata.create_all)
        assert await first.start(session_id, agent_id, user_id, team_id, "turn")
        accepted = await asyncio.gather(
            *(
                second.offer(
                    session_id, agent_id, user_id, team_id, "turn", str(i), str(i)
                )
                for i in range(12)
            )
        )
        assert all(accepted)
        deliveries = await asyncio.gather(
            first.take(session_id, "turn"), second.take(session_id, "turn")
        )
        assert sorted(
            message_id for batch in deliveries for message_id, _ in batch
        ) == [str(i) for i in sorted(range(12), key=str)]
        assert len([batch for batch in deliveries if batch]) == 1
        assert await second.offer(
            session_id, agent_id, user_id, team_id, "turn", "late", "resume me"
        )
        await first.pause(session_id, "turn")
        assert await second.start(
            session_id, agent_id, user_id, team_id, "resumed", resume=True
        )
        assert (
            await first.start(
                session_id, agent_id, user_id, team_id, "competing", resume=True
            )
            is None
        )
        await first.end(session_id, "turn", paused=True)
        assert await first.take(session_id, "resumed") == [("late", "resume me")]
    finally:
        await first.purge(session_id)
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_steering_enters_after_completed_tool_pair(monkeypatch, tmp_path) -> None:
    events = []
    monkeypatch.setattr(turn_steering, "get_stream_writer", lambda: events.append)
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    monkeypatch.setattr(turn_steering, "turn_steering_mailbox", first)
    try:
        assert await first.start("s", "a", "u", "t", "turn")
        assert await second.offer("s", "a", "u", "t", "turn", "m", "new direction")
        middleware = turn_steering.TurnSteeringMiddleware("s", "turn")
        update = await middleware.abefore_model({"messages": []}, Runtime(context=None))
        assert update is not None
        history = [
            HumanMessage(content="original"),
            AIMessage(
                content="", tool_calls=[{"name": "search", "args": {}, "id": "call-1"}]
            ),
            ToolMessage(content="result", tool_call_id="call-1"),
        ]
        merged = cast(list[BaseMessage], add_messages(history, update["messages"]))
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
        await first.end("s", "turn")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_steering_route_authorizes_before_offering(
    monkeypatch, minimal_config, tmp_path
) -> None:
    first, second, first_engine, second_engine = await _replicas(tmp_path)
    monkeypatch.setattr(turn_steering, "turn_steering_mailbox", second)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", second)
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
            "steering_turn_id": "turn",
            "agent_instance_id": "agent",
            "runtime_context": {"space_id": "space"},
        }
    )
    args = {
        "session_id": "route-steer",
        "request": request,
        "message_id": "message",
        "authenticated_user": SimpleNamespace(uid="user"),
        "container": PodApplicationContext(minimal_config),
    }
    try:
        with pytest.raises(HTTPException) as unavailable:
            await endpoint(**args)
        assert unavailable.value.status_code == 409
        assert checked == ["owner", "execution"]
        assert await first.start("route-steer", "agent", "user", "space", "turn")
        assert await endpoint(**args) == {"status": "pending"}
        assert await first.take("route-steer", "turn") == [("message", "new direction")]
        await first.end("route-steer", "turn")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()
