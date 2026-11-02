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
        assert await second.offer("s", "agent", "user", "team", "old", "m", "pending")
        yield {"kind": "awaiting_human"}

    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", exchange_id)
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", events)
    stream = agent_app_module._stream(
        cast(ReActAgentDefinition, SimpleNamespace(agent_id="agent")),
        agent_app_module._AgentExecuteRequest(
            agent_instance_id="agent",
            message="hello",
            context={"session_id": "s", "user_id": "user", "team_id": "team"},
            steering_turn_id="old",
        ),
        team_id="team",
        container=cast(PodApplicationContext, SimpleNamespace()),
    )
    try:
        assert "awaiting_human" in await anext(stream)
        assert await second.start("s", "agent", "user", "team", "new", resume=True)
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
    try:
        with pytest.raises(HTTPException) as unavailable:
            await endpoint(**args)
        assert unavailable.value.status_code == 409
        assert checked == ["owner", "execution"]
        assert await first.start("route-steer", "agent", "user", "team", "turn")
        assert await endpoint(**args) == {"status": "pending"}
        assert await first.take("route-steer", "turn") == [("message", "new direction")]
        await first.end("route-steer", "turn")
    finally:
        await first_engine.dispose()
        await second_engine.dispose()


@pytest.mark.asyncio
async def test_durable_queue_survives_expiry_and_requires_explicit_offer(tmp_path):
    first, second, engine, other = await _replicas(tmp_path)
    try:
        await first.modify("s", "a", "u", "t", "m", "keep me", "enqueue")
        await first.modify("s", "a", "u", "t", "m", "keep me", "enqueue")
        await second.cleanup_expired()
        assert [item.text for item in await second.messages("s", "a", "u", "t")] == [
            "keep me"
        ]
        assert await first.start("s", "a", "u", "t", "turn")
        assert await second.take("s", "turn") == []
        await first.end("s", "turn")
        assert (await second.messages("s", "a", "u", "t"))[0].status == "waiting"
        with pytest.raises(ValueError, match="owner_mismatch"):
            await second.messages("s", "a", "other", "t")
        with pytest.raises(ValueError, match="owner_mismatch"):
            await second.modify("s", "a", "other", "t", "m2", "wrong", "enqueue")
        assert await second.start("s", "a", "other", "t", "wrong") is None
    finally:
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
async def test_claim_is_fifo_uncertain_and_old_ack_cannot_erase_retry(tmp_path):
    first, second, engine, other = await _replicas(tmp_path)
    try:
        for item in ("1", "2"):
            await first.modify("s", "a", "u", "t", item, item, "enqueue")
        assert not await first.start(
            "s", "a", "u", "t", "wrong", queued_message_id="2", text="2"
        )
        assert await first.start(
            "s", "a", "u", "t", "one", queued_message_id="1", text="1"
        )
        assert not await second.start(
            "s", "a", "u", "t", "duplicate", queued_message_id="1", text="1"
        )
        with pytest.raises(ValueError, match="turn_is_active"):
            await second.modify("s", "a", "u", "t", "1", "", "retry")
        await first.end("s", "one")
        assert (await second.messages("s", "a", "u", "t"))[0].status == "uncertain"
        await second.modify("s", "a", "u", "t", "1", "", "retry")
        assert await second.start(
            "s", "a", "u", "t", "two", queued_message_id="1", text="1"
        )
        await first.delivered("s", "u", "one", {"1"})
        assert len(await first.messages("s", "a", "u", "t")) == 2
        await second.delivered("s", "u", "two", {"1"})
        assert [item.id for item in await first.messages("s", "a", "u", "t")] == ["2"]
    finally:
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
async def test_legacy_offer_survives_expiry_and_empty_rows_are_deleted(tmp_path):
    from sqlalchemy import select

    first, second, engine, other = await _replicas(tmp_path)
    try:
        await first.start("s", "a", "u", "t", "old")
        async with engine.begin() as conn:
            await conn.execute(
                update(turn_steering._turns).values(
                    pending=[{"id": "m", "text": "legacy"}],
                    expires_at=datetime(2000, 1, 1, tzinfo=UTC),
                )
            )
        await second.cleanup_expired()
        assert (await second.messages("s", "a", "u", "t"))[0].status == "waiting"
        await second.modify("s", "a", "u", "t", "m", "edited", "edit")
        assert (await first.messages("s", "a", "u", "t"))[0].text == "edited"
        await second.modify("s", "a", "u", "t", "m", "", "remove")
        await first.cleanup_expired()
        async with engine.begin() as conn:
            assert (await conn.execute(select(turn_steering._turns))).first() is None
    finally:
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_only_successful_history_write_acknowledges_claim(
    monkeypatch, tmp_path, fails
):
    from unittest.mock import AsyncMock

    first, second, engine, other = await _replicas(tmp_path)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", first)
    history = SimpleNamespace(
        next_rank=AsyncMock(return_value=0),
        save=AsyncMock(side_effect=RuntimeError("unavailable") if fails else None),
    )
    try:
        await first.modify("s", "a", "u", "t", "m", "text", "enqueue")
        await first.start(
            "s", "a", "u", "t", "turn", queued_message_id="m", text="text"
        )
        await agent_app_module._write_turn_history(
            session_id="s",
            user_id="u",
            request_message="text",
            payloads=[],
            history_store=cast(agent_app_module.HistoryStorePort, history),
            steering_turn_id="turn",
            queued_message_id="m",
        )
        assert bool(await second.messages("s", "a", "u", "t")) == fails
    finally:
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
async def test_cancelled_stream_finishes_mailbox_teardown(monkeypatch, tmp_path):
    first, second, engine, other = await _replicas(tmp_path)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", first)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(history_store=None)),
    )

    async def exchange_id(**kwargs):
        return "exchange"

    async def events(*args, **kwargs):
        yield {"kind": "status"}
        await asyncio.Event().wait()

    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", exchange_id)
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", events)
    entered, release = asyncio.Event(), asyncio.Event()
    end = first.end

    async def delayed_end(*args, **kwargs):
        entered.set()
        await release.wait()
        await end(*args, **kwargs)

    monkeypatch.setattr(first, "end", delayed_end)
    stream = agent_app_module._stream(
        cast(ReActAgentDefinition, SimpleNamespace(agent_id="a")),
        agent_app_module._AgentExecuteRequest(
            agent_instance_id="a",
            message="hi",
            context={"session_id": "s", "user_id": "u", "team_id": "t"},
            steering_turn_id="turn",
        ),
        team_id="t",
        container=cast(PodApplicationContext, SimpleNamespace()),
    )
    try:
        await first.modify("s", "a", "u", "t", "m", "keep", "enqueue")
        await anext(stream)
        closing = asyncio.create_task(stream.aclose())
        await entered.wait()
        closing.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert (await second.messages("s", "a", "u", "t"))[0].text == "keep"
        assert await second.start("s", "a", "u", "t", "replacement")
    finally:
        await stream.aclose()
        await engine.dispose()
        await other.dispose()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_postgres_queue_claims_and_sweeps_across_replicas():
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    engines = [create_async_engine(url) for _ in range(4)]
    boxes = [turn_steering.TurnSteeringMailbox(engine) for engine in engines]
    session = uuid4().hex
    try:
        async with engines[0].begin() as conn:
            await conn.run_sync(turn_steering._metadata.create_all)
        enqueues = await asyncio.gather(
            *(
                box.modify(session, "a", "u", "t", "m", "text", "enqueue")
                for box in boxes
            )
        )
        assert all(len(items) == 1 for items in enqueues)
        capacity = await asyncio.gather(
            *(
                boxes[i % len(boxes)].modify(
                    session, "a", "u", "t", f"pending-{i}", "bounded", "enqueue"
                )
                for i in range(36)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(item, ValueError) for item in capacity) == 5
        assert len(await boxes[0].messages(session, "a", "u", "t")) == 32
        claims = await asyncio.gather(
            *(
                box.start(
                    session, "a", "u", "t", str(i), queued_message_id="m", text="text"
                )
                for i, box in enumerate(boxes)
            )
        )
        assert sum(claim is not None for claim in claims) == 1
        winner = next(claim for claim in claims if claim is not None)
        await asyncio.gather(
            *(box.cleanup_expired() for box in boxes), boxes[0].renew(session, winner)
        )
        assert (await boxes[1].messages(session, "a", "u", "t"))[
            0
        ].status == "uncertain"
        await boxes[0].end(session, winner)
        await asyncio.gather(*(box.cleanup_expired() for box in boxes))
        assert len(await boxes[2].messages(session, "a", "u", "t")) == 32
    finally:
        await boxes[0].purge(session)
        await asyncio.gather(*(engine.dispose() for engine in engines))


@pytest.mark.asyncio
async def test_queue_routes_enforce_identity_even_before_history(
    monkeypatch, minimal_config, tmp_path
):
    first, second, engine, other = await _replicas(tmp_path)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", first)

    async def allow(*args, **kwargs):
        pass

    monkeypatch.setattr(agent_app_module, "_enforce_session_ownership", allow)
    monkeypatch.setattr(agent_app_module, "_authorize_execution_or_raise", allow)
    router = agent_app_module._build_agent_router(
        registry={}, security_enabled=True, max_chat_input_chars=5000
    )
    endpoints = {
        route.endpoint.__name__: route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    args = {
        "session_id": "s",
        "authenticated_user": SimpleNamespace(uid="u"),
        "container": PodApplicationContext(minimal_config),
    }
    try:
        result = await endpoints["update_pending_message"](
            **args,
            message_id="m",
            update=turn_steering.PendingMessageUpdate(
                request="enqueue", agent_instance_id="a", team_id="t", text="saved"
            ),
        )
        assert result[0].text == "saved"
        result = await endpoints["get_pending_messages"](
            **args, agent_instance_id="a", team_id="t"
        )
        assert result[0].id == "m"
        for action in ("retry", "remove"):
            result = await endpoints["update_pending_message"](
                **args,
                message_id="m",
                update=turn_steering.PendingMessageUpdate(
                    request=action, agent_instance_id="a", team_id="t"
                ),
            )
        assert result == []
        args["authenticated_user"] = SimpleNamespace(uid="other")
        with pytest.raises(HTTPException) as denied:
            await endpoints["get_pending_messages"](
                **args, agent_instance_id="a", team_id="t"
            )
        assert denied.value.status_code == 409
    finally:
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
async def test_rejected_queue_claim_never_invokes_agent(monkeypatch, tmp_path):
    first, second, engine, other = await _replicas(tmp_path)
    monkeypatch.setattr(agent_app_module, "turn_steering_mailbox", first)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(history_store=None)),
    )

    async def exchange_id(**kwargs):
        return "exchange"

    async def forbidden(*args, **kwargs):
        pytest.fail("An unclaimed queue message must not execute")
        yield {}

    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", exchange_id)
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", forbidden)
    stream = agent_app_module._stream(
        cast(ReActAgentDefinition, SimpleNamespace(agent_id="a")),
        agent_app_module._AgentExecuteRequest(
            agent_instance_id="a",
            message="not saved",
            context={"session_id": "s", "user_id": "u", "team_id": "t"},
            steering_turn_id="turn",
            queued_message_id="missing",
        ),
        team_id="t",
        container=cast(PodApplicationContext, SimpleNamespace()),
    )
    try:
        assert "queued_message_unavailable" in await anext(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()
        await engine.dispose()
        await other.dispose()


@pytest.mark.asyncio
async def test_graph_queue_claim_and_bounded_expiry_sweep(tmp_path):
    from sqlalchemy import insert, select

    first, second, engine, other = await _replicas(tmp_path)
    try:
        await first.modify("graph", "a", "u", "t", "m", "text", "enqueue")
        assert await first.start(
            "graph",
            "a",
            "u",
            "t",
            "turn",
            queued_message_id="m",
            text="text",
            steering_enabled=False,
        )
        assert not await second.offer(
            "graph", "a", "u", "t", "turn", "x", "no steering"
        )
        await first.end("graph", "turn")
        now = datetime(2000, 1, 1, tzinfo=UTC)
        async with engine.begin() as conn:
            await conn.execute(
                insert(turn_steering._turns),
                [
                    {
                        "session_id": f"expired-{i}",
                        "turn_id": "old",
                        "agent_instance_id": "a",
                        "user_id": "u",
                        "team_id": "t",
                        "state": "active",
                        "pending": [{"id": "m", "text": "keep"}],
                        "seen": [],
                        "expires_at": now,
                    }
                    for i in range(turn_steering._CLEANUP_BATCH + 1)
                ],
            )
        await first.cleanup_expired()
        async with engine.begin() as conn:
            rows = (
                (
                    await conn.execute(
                        select(turn_steering._turns).where(
                            turn_steering._turns.c.expires_at <= datetime.now(UTC)
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert len(rows) == 1
        await second.cleanup_expired()
        assert (await second.messages("expired-0", "a", "u", "t"))[0].text == "keep"
    finally:
        await engine.dispose()
        await other.dispose()
