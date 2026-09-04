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
RUNTIME-05 Layer 2b — model-native reasoning passthrough for ReAct streaming.

These tests exercise the load-bearing pieces:
- `support.thinking` block predicates / text extraction (permissive across shapes)
- `support.thinking.strip_reasoning_from_history` replay sanitisation (the 422 fix)
- `react_message_codec.stringify_langchain_content` skipping reasoning blocks
  (the JSON-leak-into-answer fix)
- `react_stream_adapter.decode_stream_chunk` splitting reasoning from answer text,
  including the Mistral transition frame (closing think + first text in one chunk)
- `_TransportBackedReActExecutor.stream()` emitting model_native THOUGHT_* events
  in the correct order, with reasoning never reaching the answer text
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fred_runtime.react.react_message_codec import stringify_langchain_content
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_stream_adapter import (
    assistant_delta_from_stream_event,
    decode_stream_chunk,
)
from fred_runtime.support.thinking import (
    RECALLED_REASONING_PREFIX,
    content_to_text,
    extract_thinking_text,
    is_thinking_block,
    strip_reasoning_from_history,
    thread_reasoning_within_open_turn,
)
from fred_sdk.contracts.react_contract import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
)
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    ThoughtDeltaEvent,
    ThoughtEndEvent,
    ThoughtStartEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

# ---------------------------------------------------------------------------
# support.thinking — block predicates and text extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block",
    [
        {"type": "thinking", "thinking": [{"type": "text", "text": "x"}]},
        {"type": "thinking", "thinking": "x"},
        {"type": "thinking", "text": "x"},
        {"type": "reasoning", "reasoning": "x"},
    ],
)
def test_is_thinking_block_detects_reasoning_shapes(block: object) -> None:
    assert is_thinking_block(block) is True


@pytest.mark.parametrize(
    "block",
    [
        {"type": "text", "text": "hello"},
        {"text": "no type key"},
        "plain string",
        123,
    ],
)
def test_is_thinking_block_ignores_non_reasoning(block: object) -> None:
    assert is_thinking_block(block) is False


class _TextChunk:
    """Duck-typed stand-in for a provider SDK text chunk (`.text`)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _ThinkChunk:
    """Duck-typed stand-in for a provider SDK reasoning chunk (Mistral ThinkChunk)."""

    type = "thinking"

    def __init__(self, thinking: object) -> None:
        self.thinking = thinking


def test_is_thinking_block_detects_sdk_object() -> None:
    assert is_thinking_block(_ThinkChunk([{"type": "text", "text": "reason"}])) is True


def test_extract_thinking_text_from_nested_list() -> None:
    block = {
        "type": "thinking",
        "thinking": [
            {"type": "text", "text": "first "},
            {"type": "text", "text": "second"},
        ],
    }
    assert extract_thinking_text(block) == "first second"


def test_extract_thinking_text_from_string_forms() -> None:
    assert extract_thinking_text({"type": "thinking", "thinking": "a"}) == "a"
    assert extract_thinking_text({"type": "reasoning", "reasoning": "b"}) == "b"
    assert extract_thinking_text({"type": "thinking", "text": "c"}) == "c"


def test_extract_thinking_text_from_sdk_object() -> None:
    chunk = _ThinkChunk([_TextChunk("deep "), _TextChunk("thought")])
    assert extract_thinking_text(chunk) == "deep thought"


# ---------------------------------------------------------------------------
# stringify_langchain_content — reasoning must not leak into the transcript
# ---------------------------------------------------------------------------


def test_stringify_skips_thinking_blocks() -> None:
    content = [
        {
            "type": "thinking",
            "thinking": [{"type": "text", "text": "secret reasoning"}],
        },
        {"type": "text", "text": "Visible answer"},
    ]
    rendered = stringify_langchain_content(content)
    assert rendered == "Visible answer"
    assert "secret reasoning" not in rendered


def test_stringify_plain_text_unchanged() -> None:
    assert stringify_langchain_content("just text") == "just text"
    assert stringify_langchain_content([{"type": "text", "text": "a"}]) == "a"


# ---------------------------------------------------------------------------
# strip_reasoning_from_history — Layer 2c: safe replay to the model (the 422 fix)
# ---------------------------------------------------------------------------


def test_strip_reasoning_collapses_assistant_list_content() -> None:
    """The exact failure mode: a replayed assistant message with list content."""
    history = [
        HumanMessage(content="diff between Main and Swift?"),
        AIMessage(
            content=[
                {
                    "type": "thinking",
                    "thinking": [{"type": "text", "text": "let me search"}],
                },
                {"type": "text", "text": "Here is the answer."},
            ]
        ),
    ]
    sanitised = strip_reasoning_from_history(history)
    assert sanitised[1].content == "Here is the answer."
    assert isinstance(sanitised[1].content, str)


def test_strip_reasoning_handles_empty_string_list_content() -> None:
    """`content=['']` (the literal 422 payload) must collapse to ''."""
    msg = AIMessage(content=[""], tool_calls=[])
    sanitised = strip_reasoning_from_history([msg])
    assert sanitised[0].content == ""
    assert isinstance(sanitised[0].content, str)


def test_strip_reasoning_preserves_tool_calls() -> None:
    msg = AIMessage(
        content=[{"type": "thinking", "thinking": "plan"}],
        tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "call-1"}],
    )
    sanitised = strip_reasoning_from_history([msg])
    result = sanitised[0]
    assert isinstance(result, AIMessage)
    assert result.content == ""
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "search"
    assert result.tool_calls[0]["args"] == {"q": "x"}
    assert result.tool_calls[0]["id"] == "call-1"


def test_strip_reasoning_preserves_multimodal_human_message() -> None:
    """HumanMessage image blocks (CHAT-04 base64 attachments) must NOT be collapsed."""
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }
    history = [
        HumanMessage(content=[{"type": "text", "text": "what is this?"}, image_block]),
        ToolMessage(content=[{"type": "text", "text": "tool out"}], tool_call_id="c1"),
    ]
    sanitised = strip_reasoning_from_history(history)
    # Human and tool messages are returned untouched (same object).
    assert sanitised[0] is history[0]
    assert sanitised[0].content == [
        {"type": "text", "text": "what is this?"},
        image_block,
    ]
    assert sanitised[1] is history[1]


def test_strip_reasoning_leaves_string_content_assistant_untouched() -> None:
    msg = AIMessage(content="already clean")
    sanitised = strip_reasoning_from_history([msg])
    assert sanitised[0] is msg


def test_content_to_text_matches_stringify() -> None:
    blocks = [
        {"type": "thinking", "thinking": "drop me"},
        {"type": "text", "text": "keep me"},
    ]
    assert content_to_text(blocks) == "keep me" == stringify_langchain_content(blocks)


# ---------------------------------------------------------------------------
# decode_stream_chunk — split reasoning fragments from answer text
# ---------------------------------------------------------------------------


def _messages_frame(chunk: AIMessageChunk) -> tuple[AIMessageChunk, dict[str, str]]:
    """A `(chunk, metadata)` pair as produced by stream_mode='messages'."""
    return (chunk, {"langgraph_node": "agent"})


def test_decode_thinking_only_frame() -> None:
    chunk = AIMessageChunk(
        content=[
            {"type": "thinking", "thinking": [{"type": "text", "text": "planning"}]}
        ]
    )
    decoded = decode_stream_chunk(_messages_frame(chunk))
    assert decoded.thought_fragments == ("planning",)
    assert decoded.text is None


def test_decode_transition_frame_has_both() -> None:
    """The Mistral transition frame carries closing reasoning AND first text."""
    chunk = AIMessageChunk(
        content=[
            {"type": "thinking", "thinking": [{"type": "text", "text": "last bit"}]},
            {"type": "text", "text": "Hello"},
        ]
    )
    decoded = decode_stream_chunk(_messages_frame(chunk))
    assert decoded.thought_fragments == ("last bit",)
    assert decoded.text == "Hello"


def test_decode_text_only_frames() -> None:
    list_chunk = AIMessageChunk(content=[{"type": "text", "text": "answer"}])
    str_chunk = AIMessageChunk(content="answer")
    assert decode_stream_chunk(_messages_frame(list_chunk)).thought_fragments == ()
    assert decode_stream_chunk(_messages_frame(list_chunk)).text == "answer"
    assert decode_stream_chunk(_messages_frame(str_chunk)).text == "answer"


def test_decode_reasoning_content_top_level() -> None:
    """Some OpenAI-compatible gateways surface reasoning at the top level."""
    chunk = AIMessageChunk(
        content="", additional_kwargs={"reasoning_content": "top-level reasoning"}
    )
    decoded = decode_stream_chunk(_messages_frame(chunk))
    assert decoded.thought_fragments == ("top-level reasoning",)
    assert decoded.text is None


def test_decode_suppresses_tool_node_chunks() -> None:
    """Token chunks emitted by the tools node are never answer or reasoning."""
    tool_meta = (AIMessageChunk(content="x"), {"langgraph_node": "tools"})
    decoded = decode_stream_chunk(tool_meta)
    assert decoded.text is None
    assert decoded.thought_fragments == ()


def test_decode_suppresses_tool_call_chunks() -> None:
    tool_call_chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "ls", "args": "{}", "id": "1", "index": 0}],
    )
    decoded = decode_stream_chunk(_messages_frame(tool_call_chunk))
    assert decoded.text is None
    assert decoded.thought_fragments == ()


def test_decode_ignores_non_ai_message_chunk() -> None:
    assert decode_stream_chunk("not a chunk").text is None
    assert decode_stream_chunk(42).thought_fragments == ()


def test_assistant_delta_returns_text_only() -> None:
    thinking = AIMessageChunk(
        content=[{"type": "thinking", "thinking": [{"type": "text", "text": "r"}]}]
    )
    answer = AIMessageChunk(content="answer")
    assert assistant_delta_from_stream_event(_messages_frame(thinking)) is None
    assert assistant_delta_from_stream_event(_messages_frame(answer)) == "answer"


# ---------------------------------------------------------------------------
# stream() — end-to-end THOUGHT_* emission ordering
# ---------------------------------------------------------------------------


class _FakePortable:
    agent_id = "agent-1"
    session_id = "sess-1"
    team_id = "personal"
    baggage: dict[str, object] = {}


class _FakeRuntimeContext:
    pass


class _FakeBinding:
    portable_context = _FakePortable()
    runtime_context = _FakeRuntimeContext()


class _FakeServices:
    tracer = None
    metrics = None


class _FakeCompiledAgent:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def astream(
        self,
        graph_input: object,
        *,
        config: object = None,
        stream_mode: object = None,
    ) -> AsyncIterator[object]:
        for event in self._events:
            yield event


async def _run_stream(events: list[object]) -> list[object]:
    executor = _TransportBackedReActExecutor(
        compiled_agent=_FakeCompiledAgent(events),  # type: ignore[arg-type]
        binding=_FakeBinding(),  # type: ignore[arg-type]
        services=_FakeServices(),  # type: ignore[arg-type]
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )
    collected: list[object] = []
    async for event in executor.stream(input_model, ExecutionConfig()):
        collected.append(event)
    return collected


@pytest.mark.asyncio
async def test_stream_promotes_mistral_reasoning_to_thought_events() -> None:
    final_message = AIMessage(
        content=[
            {
                "type": "thinking",
                "thinking": [{"type": "text", "text": "Plan: use no tools. Done."}],
            },
            {"type": "text", "text": "Hello world"},
        ]
    )
    events = [
        _stream_frame(
            [{"type": "thinking", "thinking": [{"type": "text", "text": "Plan: "}]}]
        ),
        _stream_frame(
            [
                {
                    "type": "thinking",
                    "thinking": [{"type": "text", "text": "use no tools."}],
                }
            ]
        ),
        # transition frame: closing reasoning + first answer text together
        _stream_frame(
            [
                {"type": "thinking", "thinking": [{"type": "text", "text": " Done."}]},
                {"type": "text", "text": "Hello "},
            ]
        ),
        _stream_frame("world"),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    starts = [e for e in collected if isinstance(e, ThoughtStartEvent)]
    deltas = [e for e in collected if isinstance(e, ThoughtDeltaEvent)]
    ends = [e for e in collected if isinstance(e, ThoughtEndEvent)]
    answer = [e for e in collected if isinstance(e, AssistantDeltaRuntimeEvent)]
    finals = [e for e in collected if isinstance(e, FinalRuntimeEvent)]

    # Exactly one model-native reasoning block, opened and closed once.
    assert len(starts) == 1
    assert starts[0].source == "model_native"
    assert starts[0].phase == "planning"
    assert starts[0].title == "Model reasoning"
    assert len(ends) == 1
    assert ends[0].thought_id == starts[0].thought_id
    # Regression: duration_ms must be a real elapsed value, not always None.
    assert ends[0].duration_ms is not None
    assert ends[0].duration_ms >= 0

    # All reasoning fragments arrive as deltas of that block.
    assert "".join(d.delta for d in deltas) == "Plan: use no tools. Done."
    assert all(d.thought_id == starts[0].thought_id for d in deltas)

    # Answer text is clean and complete; reasoning never leaks into it.
    assistant_text = "".join(a.delta for a in answer)
    assert assistant_text == "Hello world"
    assert "Plan:" not in assistant_text
    assert "thinking" not in assistant_text

    # Final answer is the clean text, with the reasoning block stripped.
    assert len(finals) == 1
    assert finals[0].content == "Hello world"
    assert "Plan:" not in finals[0].content

    # The reasoning block must close before the first answer delta.
    first_answer_idx = collected.index(answer[0])
    end_idx = collected.index(ends[0])
    assert end_idx < first_answer_idx


@pytest.mark.asyncio
async def test_stream_reports_real_duration_ms_for_tool_use_thought() -> None:
    """
    Regression: `ThoughtEndEvent.duration_ms` must be a real elapsed value, not
    always `None`.

    Why this exists:
    - before this fix, every THOUGHT_END emitted by the ReAct executor left
      `duration_ms` unset, so the frontend could never show how long a tool
      call actually took (spotted live while reviewing a "Calling read query"
      thought bubble with no useful detail).
    """

    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_query", "args": {}}],
    )
    tool_result = ToolMessage(content="ok", tool_call_id="call-1", name="read_query")
    final_message = AIMessage(content="done")

    events = [
        ("updates", {"agent": {"messages": [tool_call]}}),
        ("updates", {"tools": {"messages": [tool_result]}}),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    ends = [e for e in collected if isinstance(e, ThoughtEndEvent)]
    assert len(ends) == 1
    assert ends[0].conclusion == "Done"
    assert ends[0].duration_ms is not None
    assert ends[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_stream_closes_the_reasoning_block_at_each_tool_round() -> None:
    """
    Reasoning must be cut into one block per ReAct round, not one per turn.

    A block that stays open across tool calls swallows every later round's
    reasoning, so it carries the rank of the turn's very first fragment and the
    UI can only ever draw it above the tools — the chronology of "reasoned,
    called a tool, reasoned again" is lost at the source.
    """

    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_query", "args": {}}],
    )
    tool_result = ToolMessage(content="ok", tool_call_id="call-1", name="read_query")
    final_message = AIMessage(content="done")

    events = [
        _stream_frame(
            [{"type": "thinking", "thinking": [{"type": "text", "text": "first"}]}]
        ),
        ("updates", {"agent": {"messages": [tool_call]}}),
        ("updates", {"tools": {"messages": [tool_result]}}),
        _stream_frame(
            [{"type": "thinking", "thinking": [{"type": "text", "text": "second"}]}]
        ),
        _stream_frame("done"),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    native_starts = [
        e
        for e in collected
        if isinstance(e, ThoughtStartEvent) and e.source == "model_native"
    ]
    # Two rounds of reasoning, so two distinct blocks — not one spanning both.
    assert len(native_starts) == 2
    assert native_starts[0].thought_id != native_starts[1].thought_id

    # Each round's fragments belong to that round's own block.
    deltas_by_block: dict[str, str] = {}
    for event in collected:
        if isinstance(event, ThoughtDeltaEvent):
            deltas_by_block[event.thought_id] = (
                deltas_by_block.get(event.thought_id, "") + event.delta
            )
    assert deltas_by_block[native_starts[0].thought_id] == "first"
    assert deltas_by_block[native_starts[1].thought_id] == "second"

    # Ordering is what the UI reads: the first block closes BEFORE the tool call,
    # and the second opens only AFTER the tool result.
    kinds = [type(e) for e in collected]
    first_end = next(
        i
        for i, e in enumerate(collected)
        if isinstance(e, ThoughtEndEvent)
        and e.thought_id == native_starts[0].thought_id
    )
    tool_call_idx = kinds.index(ToolCallRuntimeEvent)
    tool_result_idx = kinds.index(ToolResultRuntimeEvent)
    second_start = collected.index(native_starts[1])
    assert first_end < tool_call_idx
    assert tool_result_idx < second_start

    # Both blocks are closed by the end of the turn — neither spins forever.
    closed_ids = {e.thought_id for e in collected if isinstance(e, ThoughtEndEvent)}
    assert {s.thought_id for s in native_starts} <= closed_ids


@pytest.mark.asyncio
async def test_stream_without_reasoning_emits_no_thought_events() -> None:
    final_message = AIMessage(content="plain answer")
    events = [
        _stream_frame("plain "),
        _stream_frame("answer"),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]
    collected = await _run_stream(events)

    assert not [e for e in collected if isinstance(e, ThoughtStartEvent)]
    assert not [e for e in collected if isinstance(e, ThoughtDeltaEvent)]
    answer = "".join(
        e.delta for e in collected if isinstance(e, AssistantDeltaRuntimeEvent)
    )
    assert answer == "plain answer"


def _stream_frame(
    content: str | list[str | dict[object, object]],
) -> tuple[str, tuple[AIMessageChunk, dict[str, str]]]:
    """Build a `('messages', (chunk, metadata))` stream event."""
    return ("messages", (AIMessageChunk(content=content), {"langgraph_node": "agent"}))


# ---------------------------------------------------------------------------
# thread_reasoning_within_open_turn — candidate fix for reasoning drift
# ---------------------------------------------------------------------------


def _reasoning_message(text: str, answer: str | None = None) -> AIMessage:
    content: list[str | dict[Any, Any]] = [
        {"type": "thinking", "thinking": [{"type": "text", "text": text}]}
    ]
    if answer:
        content.append({"type": "text", "text": answer})
    return AIMessage(content=content)


def test_open_turn_reasoning_is_replayed_as_text() -> None:
    """
    The reasoning of the turn in progress must survive as ordinary text.

    Why this test exists:
    - this is the whole point of the function: today the model gets its own
      message back with the content emptied, which is what makes it re-derive
      the plan and re-issue the identical tool call
    - the `text` channel is the only one that survives both model clients, so
      the reasoning must land there and not in a `thinking` block
    """
    history = [
        HumanMessage(content="quel est le délai ?"),
        _reasoning_message("Je n'ai pas le rapport, je cherche."),
    ]

    threaded = thread_reasoning_within_open_turn(history)

    content = threaded[1].content
    assert isinstance(content, str)
    assert "Je n'ai pas le rapport, je cherche." in content
    assert content.startswith(RECALLED_REASONING_PREFIX)


def test_closed_turn_reasoning_is_still_stripped() -> None:
    """
    Reasoning from a turn the user already closed must NOT be replayed.

    Why this test exists:
    - it is the half of the GH #1780 fix that is easy to drop by accident, and
      dropping it costs context tokens on every later request for reasoning
      whose question has already been answered
    """
    history = [
        HumanMessage(content="première question"),
        _reasoning_message("réflexion périmée", answer="Première réponse."),
        HumanMessage(content="deuxième question"),
        _reasoning_message("réflexion en cours"),
    ]

    threaded = thread_reasoning_within_open_turn(history)

    closed = threaded[1].content
    assert isinstance(closed, str)
    assert "réflexion périmée" not in closed
    assert closed == "Première réponse."

    still_open = threaded[3].content
    assert isinstance(still_open, str)
    assert "réflexion en cours" in still_open


def test_threading_preserves_tool_calls_and_leaves_other_roles_alone() -> None:
    """
    Threading must not disturb `tool_calls`, nor any non-assistant message.

    Why this test exists:
    - the reasoning rides on an assistant message that also carries the tool
      call; losing the call while keeping the reasoning would break the loop
      outright rather than merely make it repeat itself
    - human/tool messages may hold multimodal content that must pass verbatim
    """
    tool_call = {
        "name": "knowledge_search",
        "args": {"query": "délai"},
        "id": "c1",
        "type": "tool_call",
    }
    message = _reasoning_message("je cherche")
    message = message.model_copy(update={"tool_calls": [tool_call]})
    human_blocks: list[str | dict[Any, Any]] = [
        {"type": "text", "text": "regarde"},
        {"type": "image_url"},
    ]
    history = [
        HumanMessage(content=human_blocks),
        message,
        ToolMessage(content="Article 4.2", tool_call_id="c1"),
    ]

    threaded = thread_reasoning_within_open_turn(history)

    assert threaded[0].content == human_blocks
    assert threaded[1].tool_calls == [tool_call]  # type: ignore[union-attr]
    assert "je cherche" in str(threaded[1].content)
    assert threaded[2].content == "Article 4.2"


def test_threading_is_a_no_op_without_reasoning() -> None:
    """
    A turn with no reasoning must come back byte-identical in content.

    Why this test exists:
    - the function runs on every model call, including the vast majority that
      involve no reasoning at all; it must not invent a marker out of nothing
    """
    history = [
        HumanMessage(content="salut"),
        AIMessage(content=[{"type": "text", "text": "Bonjour."}]),
    ]

    threaded = thread_reasoning_within_open_turn(history)

    assert threaded[1].content == "Bonjour."
    assert RECALLED_REASONING_PREFIX not in str(threaded[1].content)
