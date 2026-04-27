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
Graph steps for the test assistant — no LLM calls, pure Python routing.

Every step in this file exercises a specific SSE event path so the UI
can be validated without a real model provider or MCP server.

Scenario routing (handled by dispatch_step):
  "echo"        → dispatch routes "echo"        → echo_step        → finalize
  "hitl choice" → dispatch routes "hitl_choice" → hitl_choice_step → finalize
  "hitl text"   → dispatch routes "hitl_text"   → hitl_text_step   → finalize
  "trace"       → dispatch routes "trace"        → trace_step       → finalize
  "error"       → dispatch routes "error"        → error_step
                                                   (raises)         → finalize via on_error
  "long"        → dispatch routes "long"         → long_step        → finalize
  (other)       → dispatch routes "fallback"     → fallback_step    → finalize
"""

from __future__ import annotations

import asyncio

from fred_sdk import (
    GraphNodeContext,
    GraphNodeResult,
    HumanChoiceOption,
    StepResult,
    choice_step,
    finalize_step as _finalize_step,
    typed_node,
)

from .graph_state import TestState

# ── Step: dispatch ─────────────────────────────────────────────────────────────


@typed_node(TestState)
async def dispatch_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Classify the user message and select the test scenario branch.

    Routes (set via route_key):
      "echo"        → echo_step
      "hitl_choice" → hitl_choice_step
      "hitl_text"   → hitl_text_step
      "trace"       → trace_step
      "error"       → error_step
      "long"        → long_step
      "fallback"    → fallback_step
    """
    context.emit_status("dispatch", "Selecting test scenario.")

    text = state.latest_user_text.lower().strip()

    if text.startswith("echo"):
        scenario = "echo"
    elif text.startswith("hitl choice"):
        scenario = "hitl_choice"
    elif text.startswith("hitl text"):
        scenario = "hitl_text"
    elif text.startswith("trace"):
        scenario = "trace"
    elif text.startswith("error"):
        scenario = "error"
    elif text.startswith("long"):
        scenario = "long"
    else:
        scenario = "fallback"

    return StepResult(state_update={"scenario": scenario}, route_key=scenario)


# ── Step: echo ─────────────────────────────────────────────────────────────────


@typed_node(TestState)
async def echo_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Emit status events then echo the user message back.

    SSE events exercised: status (x3), assistant_delta, final.
    """
    context.emit_status("echo", "Receiving your message.")
    await asyncio.sleep(0.1)
    context.emit_status("echo", "Processing.")
    await asyncio.sleep(0.1)
    context.emit_status("echo", "Sending reply.")

    return StepResult(
        state_update={
            "final_text": f"Echo: {state.latest_user_text}",
            "done_reason": "echo_complete",
        }
    )


# ── Step: hitl_choice ─────────────────────────────────────────────────────────


@typed_node(TestState)
async def hitl_choice_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Pause execution and ask the user to select one of three options.

    SSE events exercised: status, awaiting_human (choice), assistant_delta, final.
    """
    context.emit_status("hitl_choice", "Preparing confirmation request.")

    choice_id = await choice_step(
        context,
        stage="test_choice",
        title="Test HITL — Binary Choice",
        question=(
            "This is a test HITL confirmation gate.\n\n"
            "The graph has paused and is waiting for your selection.\n"
            "Pick any option to resume the workflow."
        ),
        choices=[
            HumanChoiceOption(id="option_a", label="Option A — approve"),
            HumanChoiceOption(id="option_b", label="Option B — reject"),
            HumanChoiceOption(id="option_c", label="Option C — defer"),
        ],
    )

    if choice_id is None:
        return StepResult(
            state_update={
                "final_text": "HITL choice test: no selection received (None).",
                "done_reason": "hitl_choice_none",
            }
        )

    labels: dict[str, str] = {
        "option_a": "approved",
        "option_b": "rejected",
        "option_c": "deferred",
    }
    label = labels.get(choice_id, choice_id)

    return StepResult(
        state_update={
            "final_text": (
                f"HITL choice test complete. You selected: **{label}** (`{choice_id}`).\n\n"
                "The workflow resumed successfully after the HITL gate."
            ),
            "done_reason": f"hitl_choice_{choice_id}",
        }
    )


# ── Step: hitl_text ───────────────────────────────────────────────────────────


@typed_node(TestState)
async def hitl_text_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Pause execution and ask the user to type a free-text response.

    SSE events exercised: status, awaiting_human (free-text), assistant_delta, final.

    Note: free-text HITL is implemented as a single-option choice_step where the
    user's reply text is carried back in the choice_id field by the runtime.
    """
    context.emit_status("hitl_text", "Preparing free-text input request.")

    reply = await choice_step(
        context,
        stage="test_free_text",
        title="Test HITL — Free Text Input",
        question=(
            "This is a test HITL free-text gate.\n\n"
            "Type any text below and submit to resume the workflow."
        ),
        choices=[
            HumanChoiceOption(id="__free_text__", label="Your reply"),
        ],
    )

    received = reply if reply is not None else "(no reply)"

    return StepResult(
        state_update={
            "human_text_reply": received,
            "final_text": (
                f"HITL free-text test complete.\n\n"
                f"You replied: **{received}**\n\n"
                "The workflow resumed successfully after the free-text HITL gate."
            ),
            "done_reason": "hitl_text_complete",
        }
    )


# ── Step: trace ───────────────────────────────────────────────────────────────

_MOCK_SOURCES: list[dict[str, object]] = [
    {
        "uid": "test-doc-001",
        "title": "Test Assistant Reference",
        "content": (
            "The test assistant emits mock sources to let you validate "
            "SourcesPanel rendering without a real knowledge-flow backend."
        ),
        "score": 0.97,
        "file_name": "test_assistant_reference.md",
        "file_path": "apps/fred-agents/fred_agents/test_assistant/",
    },
    {
        "uid": "test-doc-002",
        "title": "SSE Event Contract",
        "content": (
            "Sources are emitted as part of the final SSE event payload "
            "and rendered by SourcesPanel in the chat UI."
        ),
        "score": 0.84,
        "file_name": "RUNTIME-EXECUTION-CONTRACT.md",
        "file_path": "docs/design/",
    },
    {
        "uid": "test-doc-003",
        "title": "VectorSearchHit Schema",
        "content": (
            "Each VectorSearchHit carries uid, title, content, score, "
            "and optional file_name / file_path metadata fields."
        ),
        "score": 0.71,
        "file_name": "vector_search.py",
        "file_path": "libs/fred-core/fred_core/store/",
    },
]

_TRACE_STREAM = (
    "Analyzing the request. "
    "The 'trace' scenario exercises multiple status events, "
    "streaming text output via assistant_delta, "
    "and mock source documents attached to the final event. "
    "This validates the SourcesPanel component "
    "and the streaming cursor behavior. "
    "Three mock source cards are included."
)


@typed_node(TestState)
async def trace_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Emit several status events, stream text word-by-word, and return mock sources.

    SSE events exercised: status (x4), assistant_delta (word stream), final (with sources).
    Sources are stored in state; build_output override converts them to VectorSearchHit.
    """
    context.emit_status("trace", "Starting trace scenario.")
    await asyncio.sleep(0.05)
    context.emit_status("trace", "Emitting streaming analysis text.")

    words = _TRACE_STREAM.split()
    for i, word in enumerate(words):
        chunk = word if i == 0 else f" {word}"
        context.emit_assistant_delta(chunk)
        await asyncio.sleep(0.04)

    context.emit_status("trace", "Attaching mock sources.")
    await asyncio.sleep(0.05)
    context.emit_status("trace", "Done.")

    return StepResult(
        state_update={
            "sources_data": _MOCK_SOURCES,
            "final_text": _TRACE_STREAM,
            "done_reason": "trace_complete",
        }
    )


# ── Step: error ───────────────────────────────────────────────────────────────


@typed_node(TestState)
async def error_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Raise an intentional exception to exercise the node_error / on_error path.

    SSE events exercised: status, node_error, final (via on_error route to finalize).
    """
    context.emit_status("error", "About to raise a deliberate error for testing.")
    await asyncio.sleep(0.1)

    raise RuntimeError(
        "This is a deliberate test error from fred.test.assistant. "
        "The runtime should catch it, emit a node_error SSE event, "
        "and route via on_error to the finalize step."
    )


# ── Step: long ────────────────────────────────────────────────────────────────

_LONG_SENTENCES = [
    "This is the long-streaming test scenario.",
    "The test assistant emits one sentence at a time with short pauses.",
    "Each sentence is appended to the assistant delta buffer by the runtime.",
    "The StreamingCursor should be visible between sentences.",
    "The ChatInputBar should remain disabled throughout the stream.",
    "Sentence six: the cursor pulses at the end of the current text.",
    "Sentence seven: no LLM is involved — this is pure Python string output.",
    "Sentence eight: the auto-scroll in ChatMessagesArea should follow the text.",
    "Sentence nine: the ThoughtTrace accordion should not appear for this scenario.",
    "Sentence ten: only plain text is emitted, no trace channels.",
    "Sentence eleven: the SourcesPanel should not appear at the end.",
    "Sentence twelve: this tests that the UI handles a long delta gracefully.",
    "Sentence thirteen: each pause is 80 ms, giving a natural typing cadence.",
    "Sentence fourteen: the runtime buffers partial text into assistant_delta events.",
    "Sentence fifteen: the final SSE event closes the stream and unlocks input.",
    "Sentence sixteen: at this point about half the test is complete.",
    "Sentence seventeen: the scroll position should stay anchored to the bottom.",
    "Sentence eighteen: the cursor disappears on the final event.",
    "Sentence nineteen: this scenario is useful for testing layout reflow.",
    "Sentence twenty: the assistant bubble should expand naturally as text grows.",
    "Sentence twenty-one: CSS overflow handling is exercised by the long reply.",
    "Sentence twenty-two: the max-width constraint on AssistantMessage should hold.",
    "Sentence twenty-three: no wrapping artefacts should appear on narrow viewports.",
    "Sentence twenty-four: the ChatMessagesArea flex container should not overflow.",
    "Sentence twenty-five: almost done with the long-streaming test.",
    "Sentence twenty-six: the final text will be assembled from all these deltas.",
    "Sentence twenty-seven: the turn_persisted event follows the final event.",
    "Sentence twenty-eight: at that point the session is saved to the control plane.",
    "Sentence twenty-nine: the session sidebar updated_at timestamp should refresh.",
    "Long-streaming scenario complete. All thirty sentences delivered.",
]


@typed_node(TestState)
async def long_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Emit 30 sentences word-by-word with short pauses to test streaming UX.

    SSE events exercised: status, assistant_delta (continuous stream), final.
    """
    context.emit_status("long", "Starting long-streaming test (30 sentences).")

    full_text = ""
    for sentence in _LONG_SENTENCES:
        for i, word in enumerate(sentence.split()):
            chunk = word if (full_text == "" and i == 0) else f" {word}"
            context.emit_assistant_delta(chunk)
            full_text += chunk
            await asyncio.sleep(0.08)

    return StepResult(
        state_update={
            "final_text": full_text,
            "done_reason": "long_complete",
        }
    )


# ── Step: fallback ────────────────────────────────────────────────────────────

_FALLBACK_TEXT = """\
**fred.test.assistant** — available test scenarios:

| Keyword prefix | What it exercises |
|---|---|
| `echo` | Status events (x3) → simple reply |
| `hitl choice` | HITL binary choice gate (3 options) |
| `hitl text` | HITL free-text input gate |
| `trace` | Status events + streamed text + mock sources (SourcesPanel) |
| `error` | Deliberate node error → on_error route |
| `long` | 30-sentence word-by-word streaming reply |

Type the keyword at the start of your message to run that scenario.
"""


@typed_node(TestState)
async def fallback_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """Return the scenario menu when no keyword matches."""
    context.emit_status("fallback", "No matching scenario — showing help.")
    return StepResult(
        state_update={
            "final_text": _FALLBACK_TEXT,
            "done_reason": "fallback_help",
        }
    )


# ── Step: finalize ────────────────────────────────────────────────────────────


@typed_node(TestState)
async def finalize_step(
    state: TestState,
    context: GraphNodeContext,
) -> GraphNodeResult:
    """Terminal step — emit final_text or a generic error message."""
    return _finalize_step(
        final_text=state.final_text
        or (
            f"Test scenario encountered a node error: {state.node_error}"
            if state.node_error
            else None
        ),
        fallback_text="Test scenario complete.",
        done_reason=state.done_reason or ("node_error" if state.node_error else None),
    )
