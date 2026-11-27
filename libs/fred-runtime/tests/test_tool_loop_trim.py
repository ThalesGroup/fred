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
"""Offline tests for ReAct model-input history compaction and measurement."""

from __future__ import annotations

from collections.abc import Sequence

from fred_runtime.support.tool_loop import (
    compact_history_to_budget,
    strip_message_names,
    total_char_len,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


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


def test_compaction_keeps_request_answer_and_followup() -> None:
    messages = [
        HumanMessage(content="Create a workbook from my CSV"),
        _ai_with_calls("read"),
        ToolMessage(content="x" * 1000, tool_call_id="read"),
        AIMessage(content="I can now build the workbook"),
        HumanMessage(content="continue"),
    ]
    compacted = compact_history_to_budget(messages, 100, total_char_len)
    assert [message.content for message in compacted] == [
        "Create a workbook from my CSV",
        "I can now build the workbook",
        "continue",
    ]
    assert messages[2].content == "x" * 1000


def test_compaction_preserves_leader_system_context() -> None:
    messages = [
        SystemMessage(content="Leader context"),
        HumanMessage(content="original task"),
        _ai_with_calls("read"),
        ToolMessage(content="x" * 1000, tool_call_id="read"),
        AIMessage(content="plan"),
        HumanMessage(content="continue"),
    ]
    compacted = compact_history_to_budget(messages, 100, total_char_len)
    assert compacted == [messages[0], messages[1], messages[4], messages[5]]


def test_compaction_does_not_change_fitting_history() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    compacted = compact_history_to_budget(messages, 100, total_char_len)
    assert all(
        before is after for before, after in zip(messages, compacted, strict=True)
    )


def test_compaction_keeps_active_tool_pair() -> None:
    messages = [
        HumanMessage(content="original task"),
        _ai_with_calls("old"),
        ToolMessage(content="x" * 1000, tool_call_id="old"),
        AIMessage(content="plan"),
        HumanMessage(content="continue"),
        _ai_with_calls("current"),
        _tool_result("current"),
    ]
    compacted = compact_history_to_budget(messages, 100, total_char_len)
    assert compacted[:2] == [messages[0], messages[3]]
    assert compacted[2:] == messages[4:]


def test_count_budget_removes_whole_older_active_rounds() -> None:
    messages = [
        HumanMessage(content="original task"),
        _ai_with_calls("first"),
        _tool_result("first"),
        _ai_with_calls("latest"),
        _tool_result("latest"),
    ]

    assert compact_history_to_budget(messages, 3, len) == [
        messages[0],
        messages[3],
        messages[4],
    ]


def test_compaction_discards_old_turns_but_keeps_latest_answer() -> None:
    messages = [
        HumanMessage(content="old request"),
        AIMessage(content="old answer"),
        HumanMessage(content="new request"),
        AIMessage(content="new plan"),
        HumanMessage(content="continue"),
    ]
    budget = total_char_len(messages[2:])
    assert compact_history_to_budget(messages, budget, total_char_len) == messages[2:]


def test_compaction_returns_oversized_protected_context_for_rejection() -> None:
    messages = [
        HumanMessage(content="original request"),
        AIMessage(content="plan"),
        HumanMessage(content="continue"),
        _ai_with_calls("current"),
        ToolMessage(content="x" * 1000, tool_call_id="current"),
    ]
    compacted = compact_history_to_budget(messages, 100, total_char_len)
    assert compacted == messages
    assert total_char_len(compacted) > 100


def test_compaction_omits_unfinished_prior_tool_round() -> None:
    messages = [
        HumanMessage(content="unfinished request"),
        _ai_with_calls("read"),
        ToolMessage(content="x" * 1000, tool_call_id="read"),
        HumanMessage(content="new request"),
    ]
    assert compact_history_to_budget(messages, 100, total_char_len) == messages[-1:]


def test_compaction_accepts_a_different_budget_measure() -> None:
    messages = [
        HumanMessage(content="count these words"),
        _ai_with_calls("tokens"),
        ToolMessage(content="many " * 100, tool_call_id="tokens"),
        AIMessage(content="one two three"),
        HumanMessage(content="continue"),
    ]

    def estimated_tokens(candidate: Sequence) -> int:
        return sum(len(str(message.content).split()) + 3 for message in candidate)

    assert (
        compact_history_to_budget(
            messages, estimated_tokens(messages), estimated_tokens
        )
        == messages
    )
    projected = [messages[0], messages[3], messages[4]]
    assert (
        compact_history_to_budget(
            messages, estimated_tokens(projected), estimated_tokens
        )
        == projected
    )


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


def test_strip_message_names_preserves_content_pairs_and_originals() -> None:
    named = AIMessage(
        content="analysis",
        name="general-purpose",
        id="assistant-1",
        tool_calls=[{"name": "lookup", "args": {"query": "x"}, "id": "call-1"}],
    )
    result = ToolMessage(content="found", tool_call_id="call-1", name="lookup")
    original = [named.model_dump(), result.model_dump()]
    stripped = strip_message_names([named, result])
    assert [message.name for message in stripped] == [None, None]
    assert stripped[0].model_dump(exclude={"name"}) == named.model_dump(
        exclude={"name"}
    )
    assert stripped[1].model_dump(exclude={"name"}) == result.model_dump(
        exclude={"name"}
    )
    assert [named.model_dump(), result.model_dump()] == original


def test_strip_message_names_preserves_unnamed_identity() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    stripped = strip_message_names(messages)
    assert all(
        before is after for before, after in zip(messages, stripped, strict=True)
    )
