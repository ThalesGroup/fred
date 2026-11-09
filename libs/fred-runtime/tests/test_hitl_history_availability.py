# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core.history.history_schema import (
    ChatMessage,
    ChatMetadata,
    HitlRequestPart,
    make_hitl_request,
    make_hitl_response,
)
from fred_runtime.app import agent_app
from fred_runtime.runtime_support.checkpoints import checkpoint_config, graph_thread_id
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.types import Interrupt
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import create_async_engine


def availability(message: ChatMessage) -> str | None:
    part = message.parts[0]
    assert isinstance(part, HitlRequestPart)
    return part.resume_status


def request(
    rank=0,
    occurrence: str | None = "call",
    interrupt: str | None = "pause",
    agent="instance",
):
    message = make_hitl_request(
        "session",
        "exchange",
        rank,
        question="Choose a style",
        choices=[],
        stage="agent_question" if occurrence else "tool_approval",
        interrupt_id=interrupt,
        occurrence_id=occurrence,
    )
    message.metadata = ChatMetadata(agent_id=agent)
    return message


def context(monkeypatch, cp):
    monkeypatch.setattr(
        agent_app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=cp)),
    )


async def seed(cp, thread="session", identities=(("pause", "call"),)):
    config = await cp.aput(
        checkpoint_config(thread_id=thread), empty_checkpoint(), {}, {}
    )
    if identities:
        await cp.aput_writes(
            config,
            [
                (
                    "__interrupt__",
                    tuple(
                        Interrupt(id=i, value={"occurrence_id": o})
                        for i, o in identities
                    ),
                )
            ],
            "tool",
        )
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_state", [None, "claimed", "expired", "started", "consumed"]
)
@pytest.mark.parametrize("graph", [False, True])
@pytest.mark.parametrize("occurrence", [None, "call"])
async def test_history_availability_shared_across_readers(
    tmp_path, monkeypatch, claim_state, graph, occurrence
):
    url = f"sqlite+aiosqlite:///{tmp_path / 'state.db'}"
    writer_engine = create_async_engine(url)
    reader_engine = create_async_engine(url)
    writer = FredSqlCheckpointer(writer_engine, prefix="v2_")
    reader = FredSqlCheckpointer(reader_engine, prefix="v2_")
    thread = graph_thread_id("session", "instance") if graph else "session"
    try:
        await seed(writer, thread, (("pause", occurrence), ("pause-2", "sibling")))
        identity = dict(
            thread_id=thread,
            checkpoint_ns="",
            interrupt_id="pause",
            occurrence_id=occurrence,
        )
        if claim_state:
            token = await writer.aclaim_hitl_resume(**identity)
            assert token
            if claim_state in ("started", "consumed"):
                assert await writer.astart_hitl_resume(**identity, claim_token=token)
            if claim_state == "consumed":
                await writer.aconsume_hitl_resume(**identity, claim_token=token)
            if claim_state == "expired":
                async with writer.store.begin() as conn:
                    await conn.execute(
                        update(writer.hitl_claim_table).values(
                            claimed_at=datetime.now(timezone.utc) - timedelta(days=7)
                        )
                    )
        context(monkeypatch, reader)
        messages = [request(occurrence=occurrence), request(1, "sibling", "pause-2")]
        before = [m.model_dump() for m in messages]
        annotated = await agent_app._annotate_hitl_availability(messages)
        expected = "pending" if claim_state in (None, "expired") else "unavailable"
        assert [availability(m) for m in annotated] == [expected, "pending"]
        assert [m.model_dump() for m in messages] == before
        async with writer.store.begin() as conn:
            rows = (await conn.execute(select(writer.hitl_claim_table))).all()
        assert len(rows) == bool(claim_state)
        if rows:
            assert rows[0].status == (
                "claimed" if claim_state == "expired" else claim_state
            )
    finally:
        await writer_engine.dispose()
        await reader_engine.dispose()


@pytest.mark.asyncio
async def test_consumed_checkpoint_without_history_response_is_unavailable(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    cp = FredSqlCheckpointer(engine, prefix="v2_")
    try:
        await seed(cp)
        await seed(cp, identities=())
        context(monkeypatch, cp)
        annotated = await agent_app._annotate_hitl_availability([request()])
        assert availability(annotated[0]) == "unavailable"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_availability_lookup_is_bounded_and_does_not_load_channel_blobs(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    cp = FredSqlCheckpointer(engine, prefix="v2_")
    try:
        identities = tuple((f"pause-{i}", f"call-{i}") for i in range(100))
        await seed(cp, identities=identities)
        context(monkeypatch, cp)
        statements = []
        event.listen(
            engine.sync_engine,
            "before_cursor_execute",
            lambda _conn, _cursor, statement, *_args: statements.append(statement),
        )
        await agent_app._annotate_hitl_availability(
            [request(i, o, p) for i, (p, o) in enumerate(identities)]
        )
        assert len(statements) == 5
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
        assert not any(
            "checkpoint_blob" in s or "channel_blob" in s for s in statements
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lookup_failures_and_legacy_identity_remain_unknown(monkeypatch):
    cp = AsyncMock(spec=FredSqlCheckpointer)
    cp.aget_hitl_resume_state.side_effect = ValueError("undecodable checkpoint")
    context(monkeypatch, cp)
    annotated = await agent_app._annotate_hitl_availability(
        [request(), request(1, None, None)]
    )
    assert [availability(m) for m in annotated] == ["unknown", "unknown"]


@pytest.mark.asyncio
async def test_only_unanswered_trailing_requests_are_inspected(monkeypatch):
    cp = AsyncMock(spec=FredSqlCheckpointer)
    cp.aget_hitl_resume_state.return_value = ([], frozenset())
    context(monkeypatch, cp)
    old = request()
    old.exchange_id = "old"
    answered = request(1)
    response = make_hitl_response(
        "session", "exchange", 2, choice_id="science-fiction", occurrence_id="call"
    )
    pending = request(3, "next", "next-pause")
    annotated = await agent_app._annotate_hitl_availability(
        [old, answered, response, pending]
    )
    assert annotated[0] is old
    assert annotated[1] is answered
    assert availability(annotated[3]) == "unavailable"
    assert cp.aget_hitl_resume_state.call_args.kwargs["occurrences"] == frozenset(
        {("next-pause", "next")}
    )
    cp.aget_hitl_resume_state.reset_mock()
    assert await agent_app._annotate_hitl_availability([]) == []
    cp.aget_hitl_resume_state.assert_not_called()


@pytest.mark.asyncio
async def test_history_uses_the_same_latest_checkpoint_order_as_admission(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ordering.db'}")
    cp = FredSqlCheckpointer(engine, prefix="v2_")
    try:
        older = await seed(cp, identities=())
        newer = await seed(cp)
        # Simulate a later-persisted checkpoint whose id sorts before the other.
        async with cp.store.begin() as conn:
            await conn.execute(
                update(cp.checkpoints_table)
                .where(
                    cp.checkpoints_table.c.checkpoint_id
                    == older["configurable"]["checkpoint_id"]
                )
                .values(created_at=datetime.now(timezone.utc) + timedelta(days=1))
            )
        context(monkeypatch, cp)
        admitted = await cp.aget_tuple(checkpoint_config(thread_id="session"))
        assert admitted is not None
        admitted_id = admitted.config.get("configurable", {}).get("checkpoint_id")
        assert admitted_id == older["configurable"]["checkpoint_id"]
        assert admitted_id != newer["configurable"]["checkpoint_id"]
        result = await agent_app._annotate_hitl_availability([request()])
        assert availability(result[0]) == "unavailable"
    finally:
        await engine.dispose()
