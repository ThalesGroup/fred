# test_session_orchestrator_restore_history.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fred_core import KeycloakUser
from fred_core.kpi import NoOpKPIWriter
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import NoOpAgentFactory
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    Role,
    SessionSchema,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.monitoring.noop_history_store import NoOpHistoryStore
from agentic_backend.core.session.noop_session_store import NoOpSessionStore

# -----------------------
# tiny helpers (test-only)
# -----------------------


def _utcnow():
    # Millisecond drift creates false negatives; clamp microseconds.
    return datetime.now(timezone.utc).replace(microsecond=0)


def _msg(
    *,
    session_id: str,
    exchange_id: str,
    rank: int,
    role: Role,
    channel: Channel,
    parts,
):
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=_utcnow(),
        role=role,
        channel=channel,
        parts=parts,
    )


def _mk_user_session():
    user = KeycloakUser(
        uid="u-1", username="tester", email="t@example.com", roles=["user"]
    )
    session = SessionSchema(
        id="s-1", user_id=user.uid, title="Restore Test", updated_at=_utcnow()
    )
    return user, session


def _mk_orchestrator(minimal_generalist_config: Configuration):
    session_store = NoOpSessionStore()
    orch = SessionOrchestrator(
        configuration=minimal_generalist_config,
        session_store=session_store,
        attachments_store=None,
        agent_factory=NoOpAgentFactory(),
        agent_manager=MagicMock(),
        history_store=NoOpHistoryStore(),
        kpi=NoOpKPIWriter(),
    )
    return orch, session_store


# -----------------------
# core tests
# -----------------------


async def test_empty_history_returns_empty(minimal_generalist_config, monkeypatch):
    """
    Fred rationale: Fast no-op when nothing to restore avoids side effects on fresh sessions.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    async def _fake_history(_sid, _u):
        return []

    monkeypatch.setattr(orch, "get_session_history", _fake_history)
    assert await orch._restore_history(user=user, session=session) == []


async def test_orders_strictly_by_rank_not_exchange(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Rank is the single source of chronological truth. Sorting by exchange_id breaks replay.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    ex1, ex2 = "zzz-ex", "aaa-ex"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=ex1,
            rank=1,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex2,
            rank=2,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U2")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    assert isinstance(out[0], HumanMessage) and "U1" in out[0].content
    assert isinstance(out[1], HumanMessage) and "U2" in out[1].content


async def test_groups_tool_calls_then_tool_result_and_text(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Tool calls are a *batch intent* on the assistant side. Group once,
    then emit ToolMessage(s) only for matching call_ids in the *same* exchange.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    ex = "ex-1"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=ex,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="c-1", name="search", args={"q": "k8s"})],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex,
            rank=2,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[
                ToolResultPart(
                    call_id="c-1",
                    ok=True,
                    content=json.dumps({"title": "Kubernetes"}, ensure_ascii=False),
                )
            ],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex,
            rank=3,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)

    assert isinstance(out[0], HumanMessage) and "U" in out[0].content
    assert isinstance(out[1], AIMessage) and isinstance(
        getattr(out[1], "tool_calls", None), list
    )
    assert getattr(out[1], "tool_calls")[0]["id"] == "c-1"
    assert isinstance(out[2], ToolMessage) and out[2].tool_call_id == "c-1"
    # tool result content gets stringified when it's not a string
    assert "Kubernetes" in out[2].content
    assert isinstance(out[3], AIMessage) and "A" in out[3].content


async def test_skips_orphan_tool_result_cross_exchange(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Tool results must never 'leak' across exchanges; otherwise the transcript lies.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e1, e2 = "e1", "e2"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e1,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e1,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="c-1", name="toolX", args={"x": 1})],
        ),
        # This result in e2 should be skipped (belongs to e1)
        _msg(
            session_id=session.id,
            exchange_id=e2,
            rank=2,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="c-1", ok=True, content="SHOULD_SKIP")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e1,
            rank=3,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="c-1", ok=True, content="OK")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    # Only one ToolMessage should make it (the valid one in e1)
    tool_msgs = [m for m in out if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1 and "OK" in tool_msgs[0].content
    assert all("SHOULD_SKIP" not in getattr(m, "content", "") for m in out)


async def test_multiple_tool_calls_in_one_exchange(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: The assistant can schedule multiple tool calls as a single batch intent.
    We emit one AIMessage(tool_calls=[...]) capturing both.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e = "e-multi"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[
                ToolCallPart(call_id="a", name="t1", args={"x": 1}),
                ToolCallPart(call_id="b", name="t2", args={"y": 2}),
            ],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=2,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="a", ok=True, content="Ra")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=3,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="b", ok=True, content="Rb")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    ai_calls = [
        m for m in out if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
    ]
    assert len(ai_calls) == 1
    ids = {c["id"] for c in ai_calls[0].tool_calls}
    assert ids == {"a", "b"}
    tool_msgs = [m for m in out if isinstance(m, ToolMessage)]
    assert {m.tool_call_id for m in tool_msgs} == {"a", "b"}


async def test_flushes_pending_calls_at_end(minimal_generalist_config, monkeypatch):
    """
    Fred rationale: If the transcript ends during planning (tool calls) we must still preserve that intent.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e = "e-end"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="tail", name="lookup", args={"k": "v"})],
        ),
        # No tool result; end of transcript.
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    assert isinstance(out[-1], AIMessage)
    assert getattr(out[-1], "tool_calls")[0]["id"] == "tail"


async def test_windowing_keeps_whole_exchanges_and_preserves_chronology(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Windowing is by *exchange*, never splitting a conversation unit; order remains by rank.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)
    orch.restore_max_exchanges = 1  # keep only the most recent exchange

    e1, e2 = "e1", "e2"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e1,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e1,
            rank=1,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e2,
            rank=2,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U2")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e2,
            rank=3,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A2")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)

    # Only e2 remains, in rank order.
    assert len(out) == 2
    assert isinstance(out[0], HumanMessage) and "U2" in out[0].content
    assert isinstance(out[1], AIMessage) and "A2" in out[1].content


async def test_args_dict_and_string_and_unparseable_string(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Args may arrive typed or serialized; we normalize to a dict and keep raw if unparseable.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e = "e-args"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="a", name="t", args={"ok": 1})],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="b", name="t", args=json.loads('{"good": 2}'))],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=2,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="c", name="t", args=json.loads('"not-json"'))],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    ai = [
        m for m in out if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
    ][0]
    calls = {c["id"]: c["args"] for c in ai.tool_calls}
    assert calls["a"] == {"ok": 1}
    assert calls["b"] == {"good": 2}
    assert calls["c"].get("_raw") == "not-json"


async def test_system_messages_are_emitted(minimal_generalist_config, monkeypatch):
    """
    Fred rationale: System scaffolding (policies, persona) is part of the replay state.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e = "e-sys"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.system,
            channel=Channel.final,
            parts=[TextPart(text="SYS")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=2,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    assert isinstance(out[0], SystemMessage) and "SYS" in out[0].content
    assert isinstance(out[1], HumanMessage)
    assert isinstance(out[2], AIMessage)


async def test_tool_result_emits_only_after_flushing_calls(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: On a tool result, we first ensure the grouped AI(tool_calls=[...]) exists before ToolMessage.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    e = "e-order"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="x", name="t", args={"k": "v"})],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="x", ok=True, content="R")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    assert (
        isinstance(out[0], AIMessage) and getattr(out[0], "tool_calls")[0]["id"] == "x"
    )
    assert isinstance(out[1], ToolMessage) and out[1].tool_call_id == "x"


async def test_ignores_unrelated_roles_or_channels_safely(
    minimal_generalist_config, monkeypatch
):
    """
    Fred rationale: Defensive parsing—unknown shapes should not crash nor pollute the transcript.
    """
    orch, store = _mk_orchestrator(minimal_generalist_config)
    user, session = _mk_user_session()
    await store.save(session)

    # Simulate odd channel ordering and a no-op tool_result with unknown call_id.
    e = "e-odd"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=0,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="ghost", ok=True, content="skip")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=1,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=e,
            rank=2,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    out = await orch._restore_history(user=user, session=session)
    assert isinstance(out[0], HumanMessage) and "U" in out[0].content
    assert isinstance(out[1], AIMessage) and "A" in out[1].content
    assert all(not isinstance(m, ToolMessage) for m in out)


async def test_sample_from_prompt_checks(
    minimal_generalist_config, app_context, monkeypatch
):
    """
    Integration-flavored check mirroring your provided example to catch regressions.
    """
    # This test mirrors your initial "orders by rank and groups tool calls" example.
    session_store = NoOpSessionStore()
    orch = SessionOrchestrator(
        configuration=minimal_generalist_config,
        session_store=session_store,
        attachments_store=None,
        agent_factory=NoOpAgentFactory(),
        agent_manager=MagicMock(),
        history_store=NoOpHistoryStore(),
        kpi=NoOpKPIWriter(),
    )
    user = KeycloakUser(
        uid="user-1", username="tester", email="tester@example.com", roles=["user"]
    )
    session = SessionSchema(
        id="sess-1", user_id=user.uid, title="Ordering Test", updated_at=_utcnow()
    )
    await session_store.save(session)

    ex1, ex2 = "zzz-ex-1", "aaa-ex-2"
    hist = [
        _msg(
            session_id=session.id,
            exchange_id=ex1,
            rank=0,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U-e1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex1,
            rank=1,
            role=Role.assistant,
            channel=Channel.tool_call,
            parts=[ToolCallPart(call_id="call-1", name="toolX", args={"x": 1})],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex1,
            rank=2,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="call-1", ok=True, content="R1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex1,
            rank=3,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A-e1")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex2,
            rank=4,
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text="U-e2")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex2,
            rank=5,
            role=Role.tool,
            channel=Channel.tool_result,
            parts=[ToolResultPart(call_id="call-1", ok=True, content="SHOULD_SKIP")],
        ),
        _msg(
            session_id=session.id,
            exchange_id=ex2,
            rank=6,
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text="A-e2")],
        ),
    ]

    async def _fake_history(_sid, _u):
        return hist

    monkeypatch.setattr(orch, "get_session_history", _fake_history)

    lc_messages = await orch._restore_history(user=user, session=session)
    assert isinstance(lc_messages[0], HumanMessage) and "U-e1" in lc_messages[0].content
    assert (
        isinstance(lc_messages[1], AIMessage)
        and getattr(lc_messages[1], "tool_calls")[0]["id"] == "call-1"
    )
    assert (
        isinstance(lc_messages[2], ToolMessage)
        and lc_messages[2].tool_call_id == "call-1"
        and "R1" in lc_messages[2].content
    )
    assert isinstance(lc_messages[3], AIMessage) and "A-e1" in lc_messages[3].content
    assert isinstance(lc_messages[4], HumanMessage) and "U-e2" in lc_messages[4].content
    assert isinstance(lc_messages[5], AIMessage) and "A-e2" in lc_messages[5].content
    assert all(
        not (isinstance(m, ToolMessage) and "SHOULD_SKIP" in (m.content or ""))
        for m in lc_messages
    )
