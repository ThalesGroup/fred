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

from fred_runtime.support.tool_loop import trim_to_human_boundary
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _ai_with_calls(*call_ids: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "read_query", "args": {}, "id": cid} for cid in call_ids],
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
