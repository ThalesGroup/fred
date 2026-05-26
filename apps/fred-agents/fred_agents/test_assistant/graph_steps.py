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
  "think"       → dispatch routes "think"        → think_step       → finalize
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
    TuningValue,
    choice_step,
    typed_node,
)
from fred_sdk import (
    finalize_step as _finalize_step,
)
from langchain_core.messages import HumanMessage, SystemMessage

from .graph_state import TestState


def _as_int(val: TuningValue | None, default: int) -> int:
    return int(val) if isinstance(val, (int, float)) else default


def _as_bool(val: TuningValue | None, default: bool = False) -> bool:
    return val if isinstance(val, bool) else default


def _as_text(val: TuningValue | None) -> str:
    return val.strip() if isinstance(val, str) else ""


def _delay_seconds(context: GraphNodeContext) -> float:
    return _as_int(context.tuning_values.get("settings.delay_ms"), 0) / 1000.0


def _active_tuning_lines(context: GraphNodeContext) -> list[str]:
    """
    Return one compact markdown summary of every tuning field the test assistant exposes.

    Why this helper exists:
    - the fallback and model-probe scenarios show the full active tuning surface
      so developers can confirm end-to-end that every field type is stored and
      forwarded correctly by the control-plane and runtime

    How to use it:
    - call from any step that wants to append a user-visible debug dump

    Example:
    - `lines = _active_tuning_lines(context)`
    """

    # Prompts
    system_prompt = _as_text(context.tuning_values.get("prompts.system"))
    planning = _as_text(context.tuning_values.get("prompts.planning"))
    routing = _as_text(context.tuning_values.get("prompts.routing"))
    # Settings — existing scalars
    verbose = _as_bool(context.tuning_values.get("settings.verbose"))
    delay_ms = _as_int(context.tuning_values.get("settings.delay_ms"), 0)
    # Settings — new types
    greeting = _as_text(context.tuning_values.get("settings.greeting"))
    language = _as_text(context.tuning_values.get("settings.language")) or "en"
    timeout_s = context.tuning_values.get("settings.timeout_s")
    notes_raw = _as_text(context.tuning_values.get("settings.notes"))
    notes = (notes_raw[:40] + "…") if len(notes_raw) > 40 else notes_raw
    tags = context.tuning_values.get("settings.tags")
    # Credentials — mask secret, show url
    api_key_set = bool(context.tuning_values.get("credentials.api_key"))
    webhook_url = _as_text(context.tuning_values.get("credentials.webhook_url"))
    # Chat options
    allow_files = _as_bool(context.tuning_values.get("chat_options.attach_files"))
    allow_libraries = _as_bool(
        context.tuning_values.get("chat_options.libraries_selection")
    )
    return [
        "**Active tuning values:**",
        "",
        "**Prompts**",
        f"- `prompts.system` (prompt): {system_prompt or '_not set_'}",
        f"- `prompts.planning` (prompt): {planning or '_not set_'}",
        f"- `prompts.routing` (prompt): {routing or '_not set_'}",
        "",
        "**Settings**",
        f"- `settings.verbose` (boolean): {verbose}",
        f"- `settings.delay_ms` (integer): {delay_ms}",
        f"- `settings.greeting` (string): {greeting or '_not set_'}",
        f"- `settings.language` (select): {language}",
        f"- `settings.timeout_s` (number): {timeout_s if timeout_s is not None else '_not set_'}",
        f"- `settings.notes` (text-multiline): {notes or '_not set_'}",
        f"- `settings.tags` (array): {tags or '_not set_'}",
        "",
        "**Credentials**",
        f"- `credentials.api_key` (secret): {'••••••' if api_key_set else '_not set_'}",
        f"- `credentials.webhook_url` (url): {webhook_url or '_not set_'}",
        "",
        "**Chat options**",
        f"- `chat_options.attach_files` (boolean): {allow_files}",
        f"- `chat_options.libraries_selection` (boolean): {allow_libraries}",
    ]


def _model_probe_operation(user_text: str) -> str:
    """
    Derive the model-routing operation label from the scenario keyword prefix.

    Why this helper exists:
    - the test assistant needs one deterministic way to exercise different
      routing-policy operation labels without turning model selection into a
      generic tuning field

    How to use it:
    - pass the lower-cased user text routed to the `model_probe` scenario
    - returns one stable operation label such as `routing` or `planning`

    Example:
    - `operation = _model_probe_operation("model routing explain this")`
    """

    if user_text.startswith("model planning"):
        return "planning"
    return "routing"


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
      "model_probe" → model_probe_step
      "hitl_choice" → hitl_choice_step
      "hitl_text"   → hitl_text_step
      "trace"       → trace_step
      "error"       → error_step
      "long"        → long_step
      "fallback"    → fallback_step
    """
    planning = context.tuning_values.get("prompts.planning", "")
    detail = (
        f"Selecting test scenario. {planning}".strip()
        if planning
        else "Selecting test scenario."
    )
    context.emit_status("dispatch", detail)

    text = state.latest_user_text.lower().strip()

    if text.startswith("echo"):
        scenario = "echo"
    elif text.startswith("model"):
        scenario = "model_probe"
    elif text.startswith("hitl choice"):
        scenario = "hitl_choice"
    elif text.startswith("hitl text"):
        scenario = "hitl_text"
    elif text.startswith("trace"):
        scenario = "trace"
    elif text.startswith("error"):
        scenario = "error"
    elif text.startswith("think"):
        scenario = "think"
    elif text.startswith("markdown"):
        scenario = "markdown"
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
    Appends system-prompt and verbose footer when those tuning values are set.
    """
    delay = _delay_seconds(context)
    verbose = _as_bool(context.tuning_values.get("settings.verbose"))
    system_prompt = _as_text(context.tuning_values.get("prompts.system"))
    greeting = _as_text(context.tuning_values.get("settings.greeting"))

    context.emit_status("echo", "Receiving your message.")
    await asyncio.sleep(0.1 + delay)
    context.emit_status("echo", "Processing.")
    await asyncio.sleep(0.1 + delay)
    context.emit_status("echo", "Sending reply.")

    reply = f"Echo: {state.latest_user_text}"
    if greeting:
        reply = f"{greeting}\n\n{reply}"
    if system_prompt:
        reply += f"\n\n---\n**Active system prompt:** {system_prompt}"
    if verbose:
        reply += "\n\n_[verbose] scenario: echo_"

    return StepResult(
        state_update={
            "final_text": reply,
            "done_reason": "echo_complete",
        }
    )


# ── Step: model_probe ─────────────────────────────────────────────────────────


@typed_node(TestState)
async def model_probe_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Optionally invoke a model with an explicit operation label for routing tests.

    SSE events exercised:
    - status
    - assistant_delta when a model is configured
    - final

    This branch is intentionally optional: when no model provider is configured,
    it returns a deterministic explanatory message instead of failing the whole
    test assistant.
    """
    operation = _model_probe_operation(state.latest_user_text.lower().strip())
    context.emit_status(
        "model_probe",
        f"Preparing optional model probe for operation '{operation}'.",
    )
    if context.model is None:
        lines = [
            (
                "Model probe skipped: no chat model is configured for this pod. "
                "All other test-assistant scenarios remain fully offline."
            ),
            "",
            "---",
            *_active_tuning_lines(context),
        ]
        return StepResult(
            state_update={
                "final_text": "\n".join(lines),
                "done_reason": "model_probe_no_model",
            }
        )

    delay = _delay_seconds(context)
    system_prompt = _as_text(context.tuning_values.get("prompts.system"))
    phase_prompt_key = (
        "prompts.planning" if operation == "planning" else "prompts.routing"
    )
    phase_prompt = _as_text(context.tuning_values.get(phase_prompt_key))
    verbose = _as_bool(context.tuning_values.get("settings.verbose"))

    instruction_lines = [
        "You are Fred's graph-agent model-routing probe.",
        "Reply in one concise sentence.",
        f"Confirm that the requested operation label is '{operation}'.",
    ]
    if system_prompt:
        instruction_lines.append(f"Global system prompt override: {system_prompt}")
    if phase_prompt:
        instruction_lines.append(f"Phase-specific prompt: {phase_prompt}")

    response = await context.invoke_model(
        messages=[
            SystemMessage(content="\n".join(instruction_lines)),
            HumanMessage(
                content=(
                    "This is a runtime routing validation turn. "
                    f"Original user message: {state.latest_user_text}"
                )
            ),
        ],
        operation=operation,
    )
    response_text = (
        response.content if isinstance(response.content, str) else str(response.content)
    )
    lines = [
        f"Model probe complete for operation **`{operation}`**.",
        "",
        response_text,
    ]
    if verbose:
        lines += ["", "---", *_active_tuning_lines(context)]
    await asyncio.sleep(delay)
    return StepResult(
        state_update={
            "final_text": "\n".join(lines),
            "done_reason": f"model_probe_{operation}",
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
    "See the test assistant reference [1] for details on what is exercised. "
    "The SSE event contract [2] describes the wire format used. "
    "Each VectorSearchHit [3] carries uid, title, content and score."
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
    delay = _delay_seconds(context)
    context.emit_status("trace", "Starting trace scenario.")
    await asyncio.sleep(0.05 + delay)
    context.emit_status("trace", "Emitting streaming analysis text.")

    words = _TRACE_STREAM.split()
    for i, word in enumerate(words):
        chunk = word if i == 0 else f" {word}"
        context.emit_assistant_delta(chunk)
        await asyncio.sleep(0.04 + delay)

    context.emit_status("trace", "Attaching mock sources.")
    await asyncio.sleep(0.05 + delay)
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
    delay = _delay_seconds(context)
    context.emit_status("error", "About to raise a deliberate error for testing.")
    await asyncio.sleep(0.1 + delay)

    raise RuntimeError(
        "This is a deliberate test error from fred.github.test_assistant. "
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
    delay = _delay_seconds(context)
    context.emit_status("long", "Starting long-streaming test (30 sentences).")

    full_text = ""
    for sentence in _LONG_SENTENCES:
        for i, word in enumerate(sentence.split()):
            chunk = word if (full_text == "" and i == 0) else f" {word}"
            context.emit_assistant_delta(chunk)
            full_text += chunk
            await asyncio.sleep(0.08 + delay)

    return StepResult(
        state_update={
            "final_text": full_text,
            "done_reason": "long_complete",
        }
    )


# ── Step: markdown ────────────────────────────────────────────────────────────

_MARKDOWN_PAYLOAD = """\
## Rich Content Rendering Test

This reply exercises every content type the chat renderer must handle.
No LLM required — content is static.

---

### 1 — Fenced code block

```python
def fibonacci(n: int) -> list[int]:
    '''Return the first n Fibonacci numbers.'''
    seq: list[int] = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]

print(fibonacci(10))  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
```

---

### 2 — Mermaid diagram

```mermaid
graph TD
    A[User message] --> B{dispatch_step}
    B -->|markdown| C[markdown_step]
    B -->|echo| D[echo_step]
    C --> E[finalize_step]
    D --> E
```

---

### 3 — GFM table

| Scenario | Keyword | Events exercised |
|---|---|---|
| Echo | `echo` | status × 3, assistant_delta, final |
| HITL choice | `hitl choice` | status, awaiting_human, final |
| Long stream | `long` | status, assistant_delta × 30, final |

---

### 4 — GeoJSON (map)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [2.3522, 48.8566] },
      "properties": { "name": "Paris" }
    },
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [13.4050, 52.5200] },
      "properties": { "name": "Berlin" }
    },
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[2.33,48.85],[2.37,48.85],[2.37,48.87],[2.33,48.87],[2.33,48.85]]]
      },
      "properties": { "name": "Test zone", "color": "#6366f1", "fillOpacity": 0.2 }
    }
  ]
}
```

---

### 5 — Inline math

The quadratic formula: $x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$ for $ax^2 + bx + c = 0$.

---

### 6 — Block math

$$
\\sum_{k=1}^{n} k = \\frac{n(n+1)}{2}
$$

---

### 7 — Details / collapsible

:::details[Implementation notes]
Rendered by `remark-directive`. Hidden by default; expands on click.
Until wired into `MarkdownRenderer`, this block renders as plain text.
:::
"""


@typed_node(TestState)
async def markdown_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Emit a static reply containing all rich content types the renderer must handle.

    Content: fenced code (Python), Mermaid diagram, GFM table, GeoJSON
    FeatureCollection, KaTeX inline math, KaTeX block math, :::details collapsible.

    SSE events exercised: status, final.
    No LLM required.
    """
    delay = _delay_seconds(context)
    context.emit_status("markdown", "Emitting rich content rendering test payload.")
    await asyncio.sleep(0.05 + delay)
    return StepResult(
        state_update={
            "final_text": _MARKDOWN_PAYLOAD,
            "done_reason": "markdown_complete",
        }
    )


# ── Step: think ───────────────────────────────────────────────────────────────

_THINK_FINAL = """\
**Chain-of-thought test complete.**

This scenario exercised all five `ThoughtKind` phases using the structured
`context.thinking()` / `context.emit_thought()` authoring API:

| Phase | Meaning | Emitted via |
|---|---|---|
| `planning` | Agent deciding what to do and which tools to call | `context.thinking()` streaming block |
| `tool_use` | Reasoning immediately before a tool invocation | `context.thinking()` streaming block |
| `observation` | Interpreting what a tool result means | `context.emit_thought()` one-shot |
| `reflection` | Self-correction or re-planning after an observation | `context.thinking()` streaming block |
| `synthesis` | Assembling the final answer from collected evidence | `context.thinking()` streaming block |

**Open WebUI:** each block arrives as `<think>…</think>` tags in the content
stream and is rendered natively as a collapsible Thought accordion — no plugin
or configuration needed.

**Fred chat UI:** each block additionally carries `fred.thought` metadata
(phase, title, duration_ms, conclusion) for richer per-phase visual treatment.

**Mistral and all other models:** the thinking content is entirely authored —
the model sees none of it. The wire format is identical regardless of the
underlying LLM.
"""


@typed_node(TestState)
async def think_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Exercise all five ThoughtKind phases using the structured thinking API.

    Mixes context.thinking() (streaming, with conclude()) and
    context.emit_thought() (one-shot) to demonstrate both authoring styles.

    SSE events exercised:
      THOUGHT_START / THOUGHT_DELTA / THOUGHT_END  (×4 streaming blocks)
      THOUGHT_START / THOUGHT_DELTA / THOUGHT_END  (×1 one-shot via emit_thought)
      STATUS (generic progress)
      FINAL
    """
    delay = _delay_seconds(context)
    context.emit_status("think", "Running chain-of-thought scenario.")

    # ── Phase 1: planning (streaming) ─────────────────────────────────────────
    async with context.thinking(
        "planning", title="Deciding which tools to call"
    ) as thought:
        await asyncio.sleep(0.2 + delay)
        await thought.write("The user is asking about topic X.")
        await asyncio.sleep(0.15 + delay)
        await thought.write(
            "Relevant tools available: knowledge_search, sql_query, summarizer."
        )
        await asyncio.sleep(0.15 + delay)
        await thought.write(
            "knowledge_search is the best fit for an open-domain question."
        )
        await thought.conclude("Will call knowledge_search with the user query.")

    await asyncio.sleep(0.1 + delay)

    # ── Phase 2: tool_use (streaming) ─────────────────────────────────────────
    async with context.thinking(
        "tool_use", title="Preparing knowledge_search call"
    ) as thought:
        await asyncio.sleep(0.15 + delay)
        await thought.write(
            'Composing query: "What are the main characteristics of X?"'
        )
        await asyncio.sleep(0.1 + delay)
        await thought.write("Setting top_k=5, min_score=0.7.")
        await thought.conclude("Query ready. Invoking knowledge_search.")

    await asyncio.sleep(0.1 + delay)

    # ── Phase 3: observation (one-shot via emit_thought) ──────────────────────
    context.emit_thought(
        "observation",
        "Retrieved 3 documents. Scores: 0.97, 0.84, 0.71. "
        "Top result covers the core question directly. "
        "Doc #2 provides supporting context. Doc #3 is tangential.",
        title="knowledge_search result",
        conclusion="Top two documents are sufficient. Proceeding with synthesis.",
    )

    await asyncio.sleep(0.15 + delay)

    # ── Phase 4: reflection (streaming) ──────────────────────────────────────
    async with context.thinking(
        "reflection", title="Checking source consistency"
    ) as thought:
        await asyncio.sleep(0.15 + delay)
        await thought.write("Doc #1 cites date 2023-04-12; doc #2 cites 2022-11-30.")
        await asyncio.sleep(0.1 + delay)
        await thought.write(
            "The discrepancy is minor and does not affect the core answer. "
            "Prioritising doc #1 as the more recent source."
        )
        await thought.conclude("Inconsistency noted; prioritising most recent source.")

    await asyncio.sleep(0.1 + delay)

    # ── Phase 5: synthesis (streaming) ───────────────────────────────────────
    async with context.thinking(
        "synthesis", title="Composing the final answer"
    ) as thought:
        await asyncio.sleep(0.15 + delay)
        await thought.write(
            "Combining verified facts from docs #1 and #2 into a coherent summary."
        )
        await asyncio.sleep(0.1 + delay)
        await thought.write("Adding citation markers for transparency.")
        await thought.conclude("Answer composed. Ready to deliver.")

    await asyncio.sleep(0.1 + delay)

    return StepResult(
        state_update={
            "final_text": _THINK_FINAL,
            "done_reason": "think_complete",
        }
    )


# ── Step: fallback ────────────────────────────────────────────────────────────

_SCENARIO_TABLE = """\
| Keyword prefix | What it exercises |
|---|---|
| `echo` | Status events (x3) → simple reply |
| `model routing` | Optional model call using operation label `routing` |
| `model planning` | Optional model call using operation label `planning` |
| `hitl choice` | HITL binary choice gate (3 options) |
| `hitl text` | HITL free-text input gate |
| `trace` | Status events + streamed text + inline citations [1][2][3] + mock sources + mock token usage |
| `error` | Deliberate node error → on_error route |
| `think` | Chain-of-thought: all 5 `thought_kind` values (planning → tool_use → observation → reflection → synthesis) |
| `markdown` | All rich content types: code block, Mermaid, GFM table, GeoJSON, math (inline + block), details collapsible |
| `long` | 30-sentence word-by-word streaming reply |"""


@typed_node(TestState)
async def fallback_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """Return the scenario menu plus active tuning config when no keyword matches."""
    context.emit_status("fallback", "No matching scenario — showing help.")

    lines = [
        "**fred.github.test_assistant** — available test scenarios:",
        "",
        _SCENARIO_TABLE,
        "",
    ]
    lines.append("Type the keyword at the start of your message to run that scenario.")

    lines += [
        "",
        "---",
        *_active_tuning_lines(context),
    ]

    return StepResult(
        state_update={
            "final_text": "\n".join(lines),
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
