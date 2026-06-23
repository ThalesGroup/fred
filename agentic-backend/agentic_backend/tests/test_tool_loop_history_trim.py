from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agentic_backend.core.tools.tool_loop import _trim_to_human_boundary

MAX = 10


def _ai_tool_call(call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "t", "args": {}, "id": call_id}],
    )


def _tool(call_id: str) -> ToolMessage:
    return ToolMessage(content="result", tool_call_id=call_id)


def _starts_validly_after_system(window: list) -> bool:
    """A tool message right after the system message is rejected by chat APIs."""
    return bool(window) and not isinstance(window[0], ToolMessage)


def test_under_limit_is_unchanged():
    msgs = [HumanMessage(content="q"), _ai_tool_call("a"), _tool("a")]
    assert _trim_to_human_boundary(msgs, MAX) is msgs


def test_long_single_exchange_opens_on_valid_role_not_tool():
    """
    Reproduces the websocket trace: one HumanMessage followed by many
    tool calls (incl. two parallel chart_render results) = 12 messages > MAX.
    The naive last-`MAX` window would open on an orphaned ToolMessage and the
    endpoint would raise "Unexpected role 'tool' after role 'system'". The
    question has scrolled off, so the window must open on an assistant turn.
    """
    msgs: list = [HumanMessage(content="compare the months")]
    for cid in ("ds", "q1", "q2", "q3"):
        msgs += [_ai_tool_call(cid), _tool(cid)]
    # one assistant message with two parallel tool calls → two tool results
    msgs.append(
        AIMessage(
            content="rendering",
            tool_calls=[
                {"name": "chart_render", "args": {}, "id": "c1"},
                {"name": "chart_render", "args": {}, "id": "c2"},
            ],
        )
    )
    msgs += [_tool("c1"), _tool("c2")]
    assert len(msgs) == 12

    out = _trim_to_human_boundary(msgs, MAX)

    assert _starts_validly_after_system(out)
    assert isinstance(out[0], AIMessage)


def test_window_with_recent_human_starts_at_that_human():
    # Stale exchange long enough that its Human falls outside the last MAX,
    # then a fresh question that lands inside the window.
    stale = [HumanMessage(content="old")]
    for cid in ("a", "b", "c", "d"):
        stale += [_ai_tool_call(cid), _tool(cid)]
    fresh = [HumanMessage(content="new question"), _ai_tool_call("e"), _tool("e")]
    msgs = stale + fresh
    assert len(msgs) > MAX  # ensure trimming actually engages
    out = _trim_to_human_boundary(msgs, MAX)

    assert _starts_validly_after_system(out)
    assert isinstance(out[0], HumanMessage)
    assert out[0].content == "new question"


def test_no_human_anywhere_drops_leading_orphan_tool_messages():
    msgs: list = []
    for cid in ("a", "b", "c", "d", "e", "f"):
        msgs += [_ai_tool_call(cid), _tool(cid)]
    out = _trim_to_human_boundary(msgs, MAX)

    assert _starts_validly_after_system(out)
    assert isinstance(out[0], AIMessage)


def test_trimmed_window_never_opens_on_tool_after_system():
    """End-to-end shape check: SystemMessage + trimmed must be a legal opening."""
    msgs: list = [HumanMessage(content="q")]
    for cid in ("a", "b", "c", "d", "e"):
        msgs += [_ai_tool_call(cid), _tool(cid)]
    assembled = [SystemMessage(content="sys")] + _trim_to_human_boundary(msgs, MAX)
    assert isinstance(assembled[0], SystemMessage)
    assert not isinstance(assembled[1], ToolMessage)
