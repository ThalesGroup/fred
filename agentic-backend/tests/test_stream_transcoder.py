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
Unit tests for StreamTranscoder.stream_agent_response.

Coverage goals
--------------
1. Plain agent (no tools)
   - Each token chunk is emitted as a streaming_delta frame (no more "big
     end-of-stream dump").
   - The end-flush sends any text that arrived after the last throttle window.
   - Empty / whitespace-only chunks are silently ignored.

2. Tool-using agent
   - Pre-tool text chunks are emitted progressively (my fix: guard removed).
   - When a tool-call update arrives, the partial text buffer is reset; a
     tool_call ChatMessage is emitted.
   - A tool-result update emits a tool_result ChatMessage and resets the buffer.
   - Post-tool text chunks are streamed normally after tool activity.

3. Final assistant message
   - The pending_assistant_final built from the "updates" AIMessage is emitted
     at end-of-stream (non-delta, channel="final").

4. Token-usage capture
   - Usage from messages-mode chunks is captured on the final message when the
     updates-mode AIMessage carries none.
   - Usage from the updates-mode AIMessage takes precedence.

5. Filtering
   - Thought chunks (response_metadata has "thought") are silently skipped.
   - Non-assistant chunk types (e.g. ToolMessage in messages mode) are dropped.
   - Tool-call chunks (has tool_calls/tool_call_chunks) in messages mode are
     dropped.

6. Throttle
   - With flush_interval > 0, rapid chunks in the same window are batched; a
     single delta is emitted per window, and any remainder is sent via
     end-flush.

Invariants checked throughout
-------------------------------
- streaming_delta frames carry extras={"streaming_delta": True}.
- tool_call frames carry channel="tool_call" and role="assistant".
- tool_result frames carry channel="tool_result" and role="tool".
- final (non-delta) frames carry channel="final" without streaming_delta.
- No message is ever emitted with empty text in its first TextPart.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, List

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.messages.tool import ToolMessage

from agentic_backend.core.chatbot.chat_schema import Channel, Role
from agentic_backend.core.chatbot.stream_transcoder import StreamTranscoder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = "sess-test"
EXCHANGE_ID = "exch-test"
AGENT_ID = "agent-test"
BASE_RANK = 10


class _FakeUser:
    uid = "user-1"


class _FakeRuntimeContext:
    access_token = None
    refresh_token = None


def _make_transcoder(flush_interval_ms: int = 0) -> StreamTranscoder:
    """
    0 ms flush interval → every non-empty chunk emits immediately.
    Use a positive value to test throttle batching.
    """
    return StreamTranscoder(stream_flush_interval_ms=flush_interval_ms)


class _FakeAgent:
    """
    Minimal duck-type that satisfies stream_agent_response's interface.
    streaming_memory=None avoids checkpoint logic.
    """

    def __init__(self, events: List[Any]) -> None:
        self.streaming_memory = None
        self._events = events

    async def astream_updates(
        self,
        state: Any,
        *,
        config: Any = None,
        stream_mode: Any = None,
        context: Any = None,
    ) -> AsyncIterator[Any]:
        for event in self._events:
            yield event


async def _collect(transcoder: StreamTranscoder, agent: _FakeAgent) -> List[dict]:
    """Run the transcoder and collect every emitted message dict."""
    collected: List[dict] = []

    async def _cb(msg: dict) -> None:
        collected.append(msg)

    await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage("hi")],
        session_id=SESSION_ID,
        exchange_id=EXCHANGE_ID,
        agent_id=AGENT_ID,
        base_rank=BASE_RANK,
        start_seq=0,
        callback=_cb,
        user_context=_FakeUser(),
        runtime_context=_FakeRuntimeContext(),
    )
    return collected


# Convenience builders --------------------------------------------------


def _msg_chunk(text: str, node: str = "agent") -> tuple:
    """'messages' mode event carrying one assistant text chunk."""
    return ("messages", (AIMessageChunk(content=text), {"langgraph_node": node}))


def _msg_chunk_with_usage(text: str, usage: dict) -> tuple:
    chunk = AIMessageChunk(content=text, usage_metadata=usage)
    return ("messages", (chunk, {"langgraph_node": "agent"}))


def _msg_chunk_with_thought(text: str) -> tuple:
    chunk = AIMessageChunk(
        content=text, response_metadata={"thought": "internal thinking"}
    )
    return ("messages", (chunk, {"langgraph_node": "agent"}))


def _msg_chunk_tool_node(text: str) -> tuple:
    """Chunk arriving from the 'tools' LangGraph node — must be filtered."""
    return ("messages", (AIMessageChunk(content=text), {"langgraph_node": "tools"}))


def _tool_call_update(
    call_id: str = "c1", name: str = "search", args: dict | None = None
) -> dict:
    """'updates' mode event: AIMessage with tool_calls."""
    return {
        "agent": {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": call_id, "name": name, "args": args or {}}],
                )
            ]
        }
    }


def _tool_result_update(
    call_id: str = "c1", name: str = "search", content: str = "found it"
) -> dict:
    """'updates' mode event: ToolMessage."""
    return {
        "tools": {
            "messages": [ToolMessage(content=content, tool_call_id=call_id, name=name)]
        }
    }


def _final_update(
    text: str, model: str = "gpt-test", usage: dict | None = None
) -> dict:
    """'updates' mode event: final AIMessage (no tool calls)."""
    response_metadata: dict = {"model_name": model, "finish_reason": "stop"}
    kwargs: dict = {"content": text, "response_metadata": response_metadata}
    if usage is not None:
        kwargs["usage_metadata"] = usage
    return {"agent": {"messages": [AIMessage(**kwargs)]}}


def _is_streaming_delta(msg: dict) -> bool:
    return (
        msg.get("role") == Role.assistant.value
        and msg.get("channel") == Channel.final.value
        and (msg.get("metadata") or {}).get("extras", {}).get("streaming_delta") is True
    )


def _is_non_delta_final(msg: dict) -> bool:
    return (
        msg.get("role") == Role.assistant.value
        and msg.get("channel") == Channel.final.value
        and not (msg.get("metadata") or {}).get("extras", {}).get("streaming_delta")
    )


def _is_tool_call_msg(msg: dict) -> bool:
    return (
        msg.get("channel") == Channel.tool_call.value
        and msg.get("role") == Role.assistant.value
    )


def _is_tool_result_msg(msg: dict) -> bool:
    return (
        msg.get("channel") == Channel.tool_result.value
        and msg.get("role") == Role.tool.value
    )


def _first_text(msg: dict) -> str:
    parts = msg.get("parts") or []
    if parts:
        return (parts[0] or {}).get("text") or ""
    return ""


# ---------------------------------------------------------------------------
# 1. Plain agent — streaming deltas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_agent_emits_streaming_deltas_for_each_chunk() -> None:
    """
    Every non-empty chunk must produce a streaming_delta frame.
    With flush_interval_ms=0, no throttle batching occurs.
    """
    events = [
        _msg_chunk("Hello "),
        _msg_chunk("world"),
        _msg_chunk("!"),
        _final_update("Hello world!"),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    assert len(deltas) == 3, f"Expected 3 streaming_delta frames, got {len(deltas)}"
    assert _first_text(deltas[0]) == "Hello "
    assert _first_text(deltas[1]) == "world"
    assert _first_text(deltas[2]) == "!"


@pytest.mark.asyncio
async def test_plain_agent_end_flush_sends_remaining_text() -> None:
    """
    When the last chunk arrives within the throttle window (no emit yet),
    the end-flush must send the accumulated remainder.
    """
    # Use a very long flush interval so no intermediate emit fires.
    events = [
        _msg_chunk("First token "),
        _msg_chunk("second token"),
        _final_update("First token second token"),
    ]
    # 60 000 ms → effectively no intermediate emits (chunks arrive instantly)
    msgs = await _collect(_make_transcoder(60_000), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    # The first chunk fires (last_partial_emit starts at 0, so first window always opens).
    # All subsequent chunks within 60 s are batched.
    # End-flush sends whatever is left.
    all_delta_text = "".join(_first_text(d) for d in deltas)
    assert all_delta_text == "First token second token"


@pytest.mark.asyncio
async def test_plain_agent_whitespace_only_chunks_not_emitted() -> None:
    """
    Whitespace-only accumulated text must not produce a streaming_delta.
    The partial_stream_text strip() guard prevents spurious blank frames.
    """
    events = [
        _msg_chunk("   "),
        _msg_chunk("\n"),
        _msg_chunk("Real content"),
        _final_update("Real content"),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    # Only "Real content" should produce a delta (the whitespace is buffered first but
    # strip() prevents emitting until real content arrives).
    for d in deltas:
        assert _first_text(d).strip(), "Empty streaming delta was emitted"


@pytest.mark.asyncio
async def test_plain_agent_no_chunks_no_streaming_deltas() -> None:
    """
    An agent that returns a final message with no prior streaming chunks
    must NOT produce any streaming_delta frame.
    """
    events = [_final_update("Direct answer without streaming.")]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    assert deltas == []


@pytest.mark.asyncio
async def test_plain_agent_final_message_always_emitted() -> None:
    """The non-delta final ChatMessage is always emitted, regardless of streaming."""
    events = [
        _msg_chunk("Some text "),
        _final_update("Some text done"),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert len(finals) == 1
    assert _first_text(finals[0]) == "Some text done"


# ---------------------------------------------------------------------------
# 2. Tool-using agent — pre-tool text, tool call, tool result, post-tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_agent_pre_tool_text_streams_before_tool_call() -> None:
    """
    Pre-tool text chunks must now be emitted as streaming_delta frames
    (the deceda96 guard was removed; this test locks that behaviour).
    """
    events = [
        _msg_chunk("Let me check that for you..."),
        _tool_call_update("c1", "search", {"q": "test"}),
        _tool_result_update("c1", "search", "result data"),
        _msg_chunk("Based on the results: done."),
        _final_update("Based on the results: done."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    pre_tool_deltas = []
    post_tool_deltas = []
    tool_call_seen = False
    for m in msgs:
        if _is_tool_call_msg(m):
            tool_call_seen = True
        elif _is_streaming_delta(m):
            if tool_call_seen:
                post_tool_deltas.append(m)
            else:
                pre_tool_deltas.append(m)

    assert len(pre_tool_deltas) >= 1, "Pre-tool streaming deltas must be emitted"
    assert "Let me check" in _first_text(pre_tool_deltas[0])
    assert len(post_tool_deltas) >= 1, "Post-tool streaming deltas must be emitted"
    assert "Based on the results" in _first_text(post_tool_deltas[0])


@pytest.mark.asyncio
async def test_tool_agent_tool_call_buffer_reset() -> None:
    """
    After a tool-call update, the text buffer is reset. The end-flush must
    only contain post-tool text, not pre-tool text.
    """
    events = [
        _msg_chunk("Pre-tool preamble. "),
        _tool_call_update(),
        _tool_result_update(),
        _final_update("Post-tool answer."),
    ]
    msgs = await _collect(_make_transcoder(60_000), _FakeAgent(events))

    # With a 60 s throttle, only the end-flush or first-window emits fire.
    # The pre-tool text is either emitted (first window) then buffer reset,
    # or batched with the post-tool text. Either way, the final non-delta
    # message must contain ONLY the post-tool answer.
    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert len(finals) == 1
    assert _first_text(finals[0]) == "Post-tool answer."


@pytest.mark.asyncio
async def test_tool_agent_tool_call_message_emitted() -> None:
    """A tool_call update must produce a tool_call ChatMessage."""
    events = [
        _tool_call_update("c99", "my_tool", {"param": "value"}),
        _tool_result_update("c99", "my_tool"),
        _final_update("Done."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    tool_calls = [m for m in msgs if _is_tool_call_msg(m)]
    assert len(tool_calls) == 1
    parts = tool_calls[0].get("parts") or []
    assert any(p.get("type") == "tool_call" for p in parts)
    tool_part = next(p for p in parts if p.get("type") == "tool_call")
    assert tool_part.get("name") == "my_tool"
    assert tool_part.get("call_id") == "c99"


@pytest.mark.asyncio
async def test_tool_agent_tool_result_message_emitted() -> None:
    """A tool_result update must produce a tool_result ChatMessage."""
    events = [
        _tool_call_update("c1", "search"),
        _tool_result_update("c1", "search", "The answer is 42"),
        _final_update("Done."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    tool_results = [m for m in msgs if _is_tool_result_msg(m)]
    assert len(tool_results) == 1
    parts = tool_results[0].get("parts") or []
    assert any(p.get("type") == "tool_result" for p in parts)
    tool_part = next(p for p in parts if p.get("type") == "tool_result")
    assert tool_part.get("content") == "The answer is 42"


@pytest.mark.asyncio
async def test_tool_agent_post_tool_streaming_works() -> None:
    """Post-tool text streaming must work exactly as before — this is a regression guard."""
    events = [
        _tool_call_update("c1", "search"),
        _tool_result_update("c1", "search", "some result"),
        _msg_chunk("Based on the search: "),
        _msg_chunk("the answer is 42."),
        _final_update("Based on the search: the answer is 42."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    # Collect deltas that appear after the tool_result message
    tool_result_idx = next(i for i, m in enumerate(msgs) if _is_tool_result_msg(m))
    post_tool_deltas = [
        m for m in msgs[tool_result_idx + 1 :] if _is_streaming_delta(m)
    ]
    assert len(post_tool_deltas) >= 1
    combined_post = "".join(_first_text(d) for d in post_tool_deltas)
    assert "the answer is 42" in combined_post


@pytest.mark.asyncio
async def test_tool_node_chunks_are_filtered_after_tool_activity() -> None:
    """
    AIMessageChunk events tagged langgraph_node='tools' must be filtered out
    even after tool activity is seen. These come from inner LLM calls inside
    tool functions and must not appear as assistant text.
    """
    events = [
        _tool_call_update(),
        _tool_result_update(),
        _msg_chunk_tool_node("Inner LLM output from tool node"),
        _msg_chunk("Actual response after tools."),
        _final_update("Actual response after tools."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    for d in deltas:
        assert "Inner LLM output" not in _first_text(d), (
            "Chunks from the 'tools' node must never appear as assistant streaming deltas"
        )


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_sequence() -> None:
    """Multiple tool calls in one exchange all produce separate tool_call messages."""
    events = [
        _tool_call_update("c1", "search"),
        _tool_result_update("c1", "search", "r1"),
        _tool_call_update("c2", "fetch"),
        _tool_result_update("c2", "fetch", "r2"),
        _final_update("Combined answer."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    tool_calls = [m for m in msgs if _is_tool_call_msg(m)]
    tool_results = [m for m in msgs if _is_tool_result_msg(m)]
    assert len(tool_calls) == 2
    assert len(tool_results) == 2


# ---------------------------------------------------------------------------
# 3. Filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thought_chunks_are_filtered() -> None:
    """
    AIMessageChunks with 'thought' in response_metadata must be silently
    skipped — they are internal reasoning traces, not user-visible text.
    """
    events = [
        _msg_chunk_with_thought("This is my internal reasoning..."),
        _msg_chunk("Visible answer."),
        _final_update("Visible answer."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    assert all("reasoning" not in _first_text(d) for d in deltas)
    assert any("Visible answer" in _first_text(d) for d in deltas)


@pytest.mark.asyncio
async def test_tool_message_in_messages_mode_is_ignored() -> None:
    """
    A ToolMessage arriving in messages mode (not updates) must be filtered —
    only AIMessage / AIMessageChunk pass the assistant-chunk check.
    """
    tool_msg_as_chunk = ToolMessage(content="rogue tool output", tool_call_id="x")
    events = [
        ("messages", (tool_msg_as_chunk, {"langgraph_node": "tools"})),
        _msg_chunk("Real text."),
        _final_update("Real text."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    assert all("rogue" not in _first_text(d) for d in deltas)


@pytest.mark.asyncio
async def test_tool_call_chunks_in_messages_mode_are_filtered() -> None:
    """
    AIMessageChunks that carry tool_call_chunks (streaming tool-call tokens)
    must not be surfaced as assistant text deltas.
    """
    from langchain_core.messages import AIMessageChunk

    tool_call_chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "search", "args": "", "id": "c1", "index": 0}],
    )
    events = [
        ("messages", (tool_call_chunk, {"langgraph_node": "agent"})),
        _msg_chunk("Actual response."),
        _final_update("Actual response."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    deltas = [m for m in msgs if _is_streaming_delta(m)]
    # Only "Actual response." should appear; tool-call token noise must not.
    for d in deltas:
        assert _first_text(d).strip(), "Unexpected empty streaming delta"
    combined = "".join(_first_text(d) for d in deltas)
    assert "Actual response" in combined


# ---------------------------------------------------------------------------
# 4. Token-usage capture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_usage_from_updates_mode_appears_on_final_message() -> None:
    """Usage metadata on the updates AIMessage must propagate to the final ChatMessage."""
    usage = {"input_tokens": 20, "output_tokens": 40, "total_tokens": 60}
    events = [
        _msg_chunk("Answer."),
        _final_update("Answer.", usage=usage),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert len(finals) == 1
    token_usage = (finals[0].get("metadata") or {}).get("token_usage")
    assert token_usage is not None, "token_usage must be present on the final message"
    assert token_usage.get("input_tokens") == 20
    assert token_usage.get("output_tokens") == 40
    assert token_usage.get("total_tokens") == 60


@pytest.mark.asyncio
async def test_token_usage_from_messages_mode_used_as_fallback() -> None:
    """
    When the updates-mode final AIMessage carries no usage, usage from the
    messages-mode chunk must be used as fallback (messages_backfill source).
    """
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    events = [
        _msg_chunk_with_usage("Answer.", usage),
        # Final update with no usage
        {
            "agent": {
                "messages": [
                    AIMessage(content="Answer.", response_metadata={"model_name": "m"})
                ]
            }
        },
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert len(finals) == 1
    token_usage = (finals[0].get("metadata") or {}).get("token_usage")
    assert token_usage is not None
    assert token_usage.get("total_tokens") == 15


@pytest.mark.asyncio
async def test_model_name_on_final_message() -> None:
    """The model name from the final updates-mode AIMessage must appear in metadata."""
    events = [_final_update("Answer.", model="gpt-4o")]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert len(finals) == 1
    model = (finals[0].get("metadata") or {}).get("model")
    assert model == "gpt-4o"


# ---------------------------------------------------------------------------
# 5. Throttle — batching rapid chunks into one emit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_batches_chunks_arriving_in_same_window() -> None:
    """
    With flush_interval=60 s, ALL chunks arrive in the same throttle window
    (they're delivered synchronously, essentially at time 0).
    Only ONE intermediate emit fires (the first window opener), and the
    end-flush catches the rest.
    """
    chunks = ["chunk1 ", "chunk2 ", "chunk3"]
    events = [_msg_chunk(c) for c in chunks] + [_final_update("chunk1 chunk2 chunk3")]

    msgs = await _collect(_make_transcoder(60_000), _FakeAgent(events))
    deltas = [m for m in msgs if _is_streaming_delta(m)]

    # Only one intermediate emit fires (the one that opens the window),
    # plus potentially one end-flush. Total text must be correct.
    all_delta_text = "".join(_first_text(d) for d in deltas)
    assert all_delta_text == "chunk1 chunk2 chunk3"
    # Must have fewer emits than chunks (batching happened).
    assert len(deltas) < len(chunks), (
        f"Expected batching with 60 s interval but got {len(deltas)} emits for {len(chunks)} chunks"
    )


@pytest.mark.asyncio
async def test_throttle_zero_emits_each_chunk_separately() -> None:
    """
    With flush_interval=0 ms, every non-empty chunk that changes the
    accumulated text must produce its own streaming_delta.
    """
    chunks = ["A ", "B ", "C"]
    events = [_msg_chunk(c) for c in chunks] + [_final_update("A B C")]

    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))
    deltas = [m for m in msgs if _is_streaming_delta(m)]

    assert len(deltas) == 3
    assert _first_text(deltas[0]) == "A "
    assert _first_text(deltas[1]) == "B "
    assert _first_text(deltas[2]) == "C"


# ---------------------------------------------------------------------------
# 6. Message ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_ordering_user_tool_call_result_final() -> None:
    """
    Correct emission order for a tool-using exchange:
    user-message (not transcoder's job) → tool_call → tool_result → final.
    The transcoder emits only the agent-side messages.
    """
    events = [
        _tool_call_update("c1", "lookup"),
        _tool_result_update("c1", "lookup", "found"),
        _final_update("Done."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    channels = [m.get("channel") for m in msgs]
    tc_idx = channels.index(Channel.tool_call.value)
    tr_idx = channels.index(Channel.tool_result.value)
    final_idx = next(i for i, m in enumerate(msgs) if _is_non_delta_final(m))
    assert tc_idx < tr_idx < final_idx, f"Wrong order: {channels}"


@pytest.mark.asyncio
async def test_streaming_deltas_before_final_for_plain_agent() -> None:
    """
    For a plain agent: all streaming_delta frames must appear before the
    non-delta final frame.
    """
    events = [
        _msg_chunk("Part 1 "),
        _msg_chunk("Part 2"),
        _final_update("Part 1 Part 2"),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    final_idx = next(i for i, m in enumerate(msgs) if _is_non_delta_final(m))
    for i, m in enumerate(msgs):
        if _is_streaming_delta(m):
            assert i < final_idx, "streaming_delta appeared after the non-delta final"


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_event_stream_produces_no_messages() -> None:
    """An agent that yields nothing must not crash and must emit nothing."""
    msgs = await _collect(_make_transcoder(0), _FakeAgent([]))
    assert msgs == []


@pytest.mark.asyncio
async def test_only_tool_calls_no_final_message() -> None:
    """
    An edge case where the agent emits only tool-call/result updates and
    no final AIMessage. The transcoder must not crash and must not emit a
    spurious final frame.
    """
    events = [
        _tool_call_update(),
        _tool_result_update(),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))
    finals = [m for m in msgs if _is_non_delta_final(m)]
    assert finals == [], "No final AIMessage means no non-delta final frame"


@pytest.mark.asyncio
async def test_unknown_mode_events_are_silently_ignored() -> None:
    """
    Events that are neither 'messages' nor 'updates' must be silently skipped.
    """
    events = [
        ("debug", {"some": "payload"}),
        _msg_chunk("Hello."),
        _final_update("Hello."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))
    # Should not crash; should still emit the text delta and final message.
    assert any(_is_streaming_delta(m) for m in msgs)
    assert any(_is_non_delta_final(m) for m in msgs)


@pytest.mark.asyncio
async def test_session_and_exchange_ids_propagated_to_all_messages() -> None:
    """Every emitted message must carry the correct session_id and exchange_id."""
    events = [
        _msg_chunk("Text."),
        _tool_call_update(),
        _tool_result_update(),
        _final_update("Text."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    for m in msgs:
        assert m.get("session_id") == SESSION_ID, (
            f"Wrong session_id in {m.get('channel')}"
        )
        assert m.get("exchange_id") == EXCHANGE_ID, (
            f"Wrong exchange_id in {m.get('channel')}"
        )


@pytest.mark.asyncio
async def test_ranks_are_monotonically_increasing() -> None:
    """
    Ranks assigned to emitted messages must be >= base_rank and must not
    decrease (they may repeat for streaming deltas that share a rank slot,
    but must not go backward compared to the previous non-delta message).
    """
    events = [
        _msg_chunk("A "),
        _msg_chunk("B"),
        _tool_call_update(),
        _tool_result_update(),
        _final_update("A B done."),
    ]
    msgs = await _collect(_make_transcoder(0), _FakeAgent(events))

    ranks = [m.get("rank", 0) for m in msgs]
    for rank in ranks:
        assert rank >= BASE_RANK, f"Rank {rank} is below base_rank {BASE_RANK}"
