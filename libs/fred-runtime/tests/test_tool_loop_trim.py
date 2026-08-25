# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Offline tests for history trimming in the ReAct tool loop.

Why this file exists:
- `trim_to_human_boundary` must never hand the model a payload that starts on a
  bare ToolMessage. OpenAI-compatible providers (Mistral, OpenAI) reject a
  request whose first non-system message is a tool result with no preceding
  `tool_calls`, which crashes the whole turn instead of answering the user.
- This regression is triggered when one reasoning step fans out more tool calls
  than `max_history_messages`, e.g. a batch of failed `read_query` calls: the
  tail slice then contains only orphan ToolMessages.

All tests are offline — no model or network required.
"""

from __future__ import annotations

from fred_runtime.support.tool_loop import (
    total_char_len,
    trim_to_char_budget,
    trim_to_human_boundary,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _ai_with_calls(*call_ids: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "read_query", "args": {}, "id": cid} for cid in call_ids],
    )


def _ai_proposing_write_document(call_id: str, content_markdown: str) -> AIMessage:
    """
    Shapes the motivating field incident exactly: `content` empty (LangChain
    leaves it that way on a pure tool-calling turn), the real payload in the
    tool call's own `args` (found missing from the char budget in PR review).
    """
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_document",
                "args": {"title": "doc", "content_markdown": content_markdown},
                "id": call_id,
            }
        ],
    )


def _tool_result(call_id: str) -> ToolMessage:
    return ToolMessage(content="err", tool_call_id=call_id, name="read_query")


def test_short_history_is_returned_unchanged() -> None:
    """When the history already fits the budget, it is returned as-is."""
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert trim_to_human_boundary(messages, 10) == messages


def test_window_starts_on_first_human_message() -> None:
    """A HumanMessage in the window becomes the start of the trimmed context."""
    messages = [
        AIMessage(content="old"),
        _tool_result("z"),
        HumanMessage(content="current question"),
        _ai_with_calls("a"),
        _tool_result("a"),
    ]
    trimmed = trim_to_human_boundary(messages, 3)
    assert isinstance(trimmed[0], HumanMessage)
    assert trimmed[0].content == "current question"


def test_leading_orphan_tool_messages_are_dropped() -> None:
    """
    A fan-out of tool calls larger than the budget leaves the tail slice starting
    mid tool-round. The leading orphan ToolMessages (whose AIMessage was cut off)
    must be dropped so the window never begins on a bare tool result.
    """
    # One reasoning step issues 4 tool calls; with a budget of 3 the naive tail
    # slice is [T(b), T(c), T(d)] — all orphans.
    messages = [
        HumanMessage(content="q"),
        _ai_with_calls("a", "b", "c", "d"),
        _tool_result("a"),
        _tool_result("b"),
        _tool_result("c"),
        _tool_result("d"),
    ]
    trimmed = trim_to_human_boundary(messages, 3)
    assert trimmed == [], (
        "a window made only of orphan tool results must collapse to empty, "
        f"got {[type(m).__name__ for m in trimmed]}"
    )
    assert not (trimmed and isinstance(trimmed[0], ToolMessage))


def test_window_advances_to_first_non_tool_message() -> None:
    """
    When the tail slice starts with orphan ToolMessages but then reaches a fresh
    AIMessage(tool_calls), the window starts on that AIMessage (a valid boundary),
    dropping only the leading orphans.
    """
    messages = [
        _ai_with_calls("x"),  # cut off the front
        _tool_result("x"),  # -> orphan in the window
        _ai_with_calls("y"),
        _tool_result("y"),
    ]
    trimmed = trim_to_human_boundary(messages, 3)
    assert isinstance(trimmed[0], AIMessage)
    assert trimmed[0].tool_calls[0]["id"] == "y"
    assert not isinstance(trimmed[0], ToolMessage)


# ---------------------------------------------------------------------------
# trim_to_char_budget (#2350) — size-based companion to the message-count trim
# above: a handful of large messages (a generated document, a big RAG hit)
# can blow a provider's context window while the message count stays low.
# ---------------------------------------------------------------------------


def test_char_budget_returns_unchanged_when_under_budget() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert trim_to_char_budget(messages, 1000) == messages


def test_char_budget_drops_oldest_messages_first() -> None:
    """Trailing messages are kept as long as they fit; older ones are dropped."""
    messages = [
        HumanMessage(content="q1 " + "a" * 20),
        AIMessage(content="a1 " + "b" * 20),
        HumanMessage(content="q2 " + "c" * 20),
        AIMessage(content="a2 " + "d" * 20),
    ]
    # Budget fits only the last two messages (~23 chars each).
    trimmed = trim_to_char_budget(messages, 46)
    assert trimmed == messages[-2:]
    assert total_char_len(trimmed) <= 46


def test_char_budget_always_keeps_at_least_the_last_message() -> None:
    """
    Even when the single last message alone exceeds the budget, it is kept
    rather than collapsed to an empty list — the caller (middleware) is
    responsible for detecting the still-over-budget result and failing the
    turn cleanly, not this pure trim function.
    """
    messages = [HumanMessage(content="short"), HumanMessage(content="x" * 100)]
    trimmed = trim_to_char_budget(messages, 10)
    assert trimmed == [messages[-1]]
    assert total_char_len(trimmed) > 10


def test_char_budget_advances_to_human_boundary_like_message_trim() -> None:
    """The same tool-call/tool-result pairing safety applies to the char trim."""
    messages = [
        HumanMessage(content="q" * 5),
        _ai_with_calls("a", "b", "c", "d"),
        ToolMessage(content="r" * 10, tool_call_id="a", name="read_query"),
        ToolMessage(content="r" * 10, tool_call_id="b", name="read_query"),
        ToolMessage(content="r" * 10, tool_call_id="c", name="read_query"),
        ToolMessage(content="r" * 10, tool_call_id="d", name="read_query"),
    ]
    # Budget only fits the trailing orphan ToolMessages (mid tool-round): a
    # naive tail slice would start on a bare tool result with no preceding
    # AIMessage(tool_calls) — collapsing to empty is the safe outcome.
    trimmed = trim_to_char_budget(messages, 15)
    assert trimmed == []


def test_char_budget_counts_tool_call_arguments_not_just_content() -> None:
    """
    Regression for the exact field incident (found in PR review): a
    tool-calling AIMessage's own `content` is empty, and the large payload
    lives entirely in `tool_calls[*]["args"]`. If the budget only looked at
    `content`, a `write_document` call carrying a huge document would be
    almost invisible to it — precisely defeating the point of this fix.
    """
    huge = "x" * 50_000
    messages = [
        HumanMessage(content="please write it"),
        _ai_proposing_write_document("c1", huge),
    ]
    assert total_char_len(messages) >= len(huge)

    # And the trim actually engages on it: a budget well under the
    # argument's own size must still trim, not silently let it through
    # because `content` alone was short.
    trimmed = trim_to_char_budget(messages, 100)
    assert total_char_len(trimmed) < total_char_len(messages)


def test_char_budget_never_raises_even_when_unfixable() -> None:
    """
    `trim_to_char_budget` never raises: `ChatTurnTooLargeError` is the
    middleware's responsibility once it sees the trimmed result is still
    over budget (unit-tested in the middleware layer, not here).
    """
    messages = [HumanMessage(content="x" * 1000)]
    trimmed = trim_to_char_budget(messages, 1)
    assert trimmed == messages
