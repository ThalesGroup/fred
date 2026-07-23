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
  "files"       → dispatch routes "files"        → files_step       → finalize
  "geo"         → dispatch routes "geo"          → geo_step         → finalize
  "document"    → dispatch routes "document"    → document_step    → finalize
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
from fred_sdk.contracts.context import GeoPart
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
      "files"       → files_step
      "geo"         → geo_step
      "document"    → document_step
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
    elif text.startswith("files"):
        scenario = "files"
    elif text.startswith("geo"):
        scenario = "geo"
    elif text.startswith("document"):
        scenario = "document"
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
This is the canonical directive currently supported by `MarkdownRenderer`.
:::

---

### 8 — Aligned equation (multi-line)

$$
\\begin{aligned}
  f(x) &= (x+1)^2 \\\\
       &= x^2 + 2x + 1
\\end{aligned}
$$

---

### 9 — Markdown table with math

| **Function**       | **Derivative**            | **Integral**             |
|--------------------|---------------------------|--------------------------|
| $f(x) = x^n$       | $f'(x) = n x^{n-1}$       | $\\int f(x) = \\frac{x^{n+1}}{n+1} + C$ |
| $f(x) = e^x$       | $f'(x) = e^x$             | $\\int f(x) = e^x + C$    |

---

### 10 — Syntax-highlighted code block

```python
def factorial(n: int) -> int:
    '''Compute the factorial of n recursively.'''
    return 1 if n <= 1 else n * factorial(n - 1)

# Test
print(factorial(5))  # Output: 120
```

---

### 11 — Interactive checklist

- [x] Test equation rendering
- [ ] Verify collapsible block display
- [ ] Validate tables containing LaTeX
- [ ] Simulate streaming delay (for example: 2s per block)

---

### 12 — Secondary information block

:::details[Heads-up]
This content is generated dynamically.
Equations may take **1-2 seconds** to appear when streaming is enabled.
:::

---

### 13 — ASCII chart inside a code block

````markdown
```text
       ^
       |           * (3, 6)
       |         /
       |       /
       |     /
       |   /
       | /
-------+---------->
       1 2 3 4 5
```
````

---

### 14 — Emoji + inline math

⚡ **Euler's formula**: $e^{i\\pi} + 1 = 0$ (often considered the most beautiful equation in mathematics!).

---

### 15 — "Spoiler" block (collapsible with a punchy title)

:::details[🔍 Puzzle solution...]
The answer is **42** (a classic programmer joke inspired by *The Hitchhiker's Guide to the Galaxy*).

To prove it:

$$
\\text{Why?} \\approx \\int_{\\text{life}} \\text{meaning} \\, dt = 42
$$

:::

---

### 16 — Complex combination (table + code + math)

| **Step** | **Code**                          | **Result**                 |
|-----------|-----------------------------------|----------------------------|
| 1         | `x = np.linspace(0, 2*np.pi)`     | Creates 50 points between 0 and $2\\pi$ |
| 2         | `y = np.sin(x)`                   | Computes $\\sin(x)$ for each point |
| 3         | `plt.plot(x, y)`                  | Displays the **sine wave**: |

```python
import matplotlib.pyplot as plt
plt.plot(x, y)
plt.title("y = sin(x)")
plt.show()
```

---

### 17 — Special characters and Unicode test

- **Math symbols**: ∀ ∃ ∵ ∴ ∈ ∉ ⊆ ⊂ ∪ ∩ ≅ ≈ ≠ ≤ ≥
- **Arrows**: ⇒ ⇔ ⇐ ⇒ ↦ ⤳ ⇣
- **Emoji mix**: ❄️ → $T = 0°C$ (ice melting) 🔥

---

**Note:**

These examples cover:

- Interactive blocks (collapsibles, checklists).
- Combined syntaxes (math + code + tables).
- Simulated dynamic content (delays).


### 18 — Mindmap

```mindmap-json
{
  "version": "1.0",
  "title": "Transcript\u2011to\u2011Mindmap Workflow",
  "summary": "",
  "root": {
    "id": "root",
    "name": "Workflow Overview",
    "summary": "High\u2011level process for converting a transcript into a Mermaid mindmap.",
    "detail": "",
    "evidence": [],
    "children": [
      {
        "id": "steps",
        "name": "Steps",
        "summary": "",
        "detail": "",
        "evidence": [],
        "children": [
          {
            "id": "analyze-request",
            "name": "Analyze Request",
            "summary": "",
            "detail": "Parse intent, scope, and key entities to focus retrieval.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "retrieve-chunks",
            "name": "Retrieve Chunks",
            "summary": "",
            "detail": "Vector search with high top_k; enforce token limit; fallback if empty.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "outline",
            "name": "Outline",
            "summary": "",
            "detail": "Condense excerpts into hierarchical bullet points, preserving order.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "generate-mermaid",
            "name": "Generate Mermaid",
            "summary": "",
            "detail": "Convert outline to Mermaid syntax; validate before embedding.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "produce-markdown",
            "name": "Produce Markdown",
            "summary": "",
            "detail": "Embed mindmap in Markdown; add disclaimer if partial content.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          }
        ]
      },
      {
        "id": "key-decisions",
        "name": "Key Decisions",
        "summary": "",
        "detail": "",
        "evidence": [],
        "children": [
          {
            "id": "specific-question",
            "name": "Specific Question",
            "summary": "",
            "detail": "Reduces retrieval noise and improves relevance.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "high-top-k-with-limit",
            "name": "High top_k with limit",
            "summary": "",
            "detail": "Balances completeness vs. token budget.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "honesty-flag",
            "name": "Honesty Flag",
            "summary": "",
            "detail": "Transparency when only partial data is available.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          }
        ]
      },
      {
        "id": "action-items",
        "name": "Action Items",
        "summary": "",
        "detail": "",
        "evidence": [],
        "children": [
          {
            "id": "configure-top-k",
            "name": "Configure top_k",
            "summary": "",
            "detail": "Allow adjustable parameter for retrieval depth.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "implement-fallback",
            "name": "Implement fallback",
            "summary": "",
            "detail": "Handle empty retrievals gracefully.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "add-honesty-check",
            "name": "Add honesty check",
            "summary": "",
            "detail": "Prepend disclaimer if retrieved content < full transcript.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          },
          {
            "id": "test-rendering",
            "name": "Test rendering",
            "summary": "",
            "detail": "Ensure Mermaid works in target Markdown viewer.",
            "evidence": [
              {
                "sourceIndex": 1,
                "quote": ""
              }
            ],
            "children": []
          }
        ]
      }
    ]
  },
  "presentation": {
    "initialDepth": 2,
    "layout": "orthogonal",
    "focusMode": true
  }
}
```

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

    SSE events exercised: status, assistant_delta × 2, final.
    The Mermaid fence is split across the two deltas (chunk 1 ends mid-block,
    chunk 2 delivers the closing fence + remainder) to stress-test that the
    renderer buffers an incomplete fenced block rather than attempting a
    partial render.
    No LLM required.
    """
    delay = _delay_seconds(context)
    context.emit_status("markdown", "Emitting rich content rendering test payload.")
    await asyncio.sleep(0.05 + delay)

    # Split mid-mermaid: chunk 1 ends after the second edge (no closing fence yet)
    _SPLIT_MARKER = "    B -->|markdown| C[markdown_step]\n"
    split_idx = _MARKDOWN_PAYLOAD.index(_SPLIT_MARKER) + len(_SPLIT_MARKER)

    context.emit_assistant_delta(_MARKDOWN_PAYLOAD[:split_idx])
    await asyncio.sleep(0.4 + delay)
    context.emit_assistant_delta(_MARKDOWN_PAYLOAD[split_idx:])

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


# ── Step: files ───────────────────────────────────────────────────────────────

_FILES_PATH = "outputs/sample.txt"

_FILES_SAMPLE = """\
Hello from the Test Assistant.

This file was written to your personal workspace through the unified /fs
filesystem. Send "files <your own text>" to store your own content instead.
"""


@typed_node(TestState)
async def files_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Round-trip a small text file through the unified team-rooted /fs workspace.

    Writes a file into the agent's own workspace (the Agents space — bare paths route
    to teams/{team}/agents/{instance}/users/{uid}/...), reads it back to prove the
    round-trip, then lists the directory. Exercises the workspace API
    (`write` / `read` / `ls`) — i.e. the FILES-04 unified filesystem.

    The artifact is surfaced as a `LinkPart` ui_part (not a markdown link): the
    `/fs/download` route is session-authenticated, so the chat renders the link as
    a download chip that fetches it with the live Bearer token. A plain anchor to
    the raw URL would fail with "No authentication token provided".

    Content: the text after the `files` keyword, or a built-in sample when the
    user supplies none.

    SSE events exercised: status (x3), assistant_delta, final (with ui_parts).

    This branch needs a Knowledge Flow workspace backend. When none is wired it
    degrades to an explanatory message instead of failing, preserving the test
    assistant's "runs anywhere" promise for the other scenarios.
    """
    delay = _delay_seconds(context)

    # Everything after the "files" keyword is the user-provided content.
    remainder = state.latest_user_text.strip()[len("files") :].strip()
    content = remainder or _FILES_SAMPLE
    source = "your message" if remainder else "the built-in sample"

    context.emit_status("files", f"Writing {_FILES_PATH} from {source}.")
    await asyncio.sleep(0.05 + delay)

    # Write first. The download chip is built from this artifact and is ALWAYS returned
    # when the write succeeds — even if the read-back/listing below hiccups — so the user
    # can fetch the generated file straight from the conversation, not only via the Files UI.
    try:
        artifact = await context.write(
            _FILES_PATH,
            content,
            content_type="text/plain; charset=utf-8",
            title="Test Assistant sample",
        )
    except Exception as exc:  # noqa: BLE001 — nothing was written, so there is no link
        context.emit_status("files", "Workspace backend unavailable.")
        reply = (
            "**Filesystem test could not run.**\n\n"
            "This scenario writes and reads a file through the unified `/fs` "
            "workspace, which needs a Knowledge Flow backend wired into the pod "
            f"(`RuntimeServices.workspace_fs`).\n\nError: `{type(exc).__name__}: {exc}`"
        )
        return StepResult(
            state_update={"final_text": reply, "done_reason": "files_unavailable"}
        )

    link_parts = [artifact.to_link_part().model_dump(mode="json")]

    # Best-effort verification (read-back + listing). Any failure here is reported but
    # must NOT drop the download link, since the file was already written.
    readback: str | None = None
    listing = ""
    verify_error: str | None = None
    try:
        context.emit_status("files", "Reading the file back to verify the round-trip.")
        await asyncio.sleep(0.05 + delay)
        readback = await context.read(_FILES_PATH)

        context.emit_status("files", "Listing the workspace directory.")
        entries = await context.ls("outputs")
        listing = "\n".join(
            f"- `{entry.path}` ({'dir' if entry.is_dir else f'{entry.size} bytes'})"
            for entry in entries
        )
    except Exception as exc:  # noqa: BLE001 — keep the link; just note the check failed
        verify_error = f"{type(exc).__name__}: {exc}"

    if verify_error is None:
        reply = (
            "**Filesystem round-trip complete.**\n\n"
            f"Wrote {source} to this agent's workspace (Agents space) and read it straight back. "
            "Use the download chip below to fetch it.\n\n"
            f"| Step | Result |\n|---|---|\n"
            f"| Write | {artifact.file_name} ({artifact.size} bytes) |\n"
            f"| Read back | {'matches' if readback == content else 'differs'} |\n\n"
            "**Content read back:**\n\n```\n"
            f"{readback}\n```\n\n"
            "**Directory listing (`outputs/`):**\n\n"
            f"{listing or '_empty_'}"
        )
    else:
        reply = (
            "**File generated.**\n\n"
            f"Wrote {source} to this agent's workspace (Agents space) as "
            f"`{artifact.file_name}` ({artifact.size} bytes). Use the download chip below to fetch it.\n\n"
            f"_The read-back/listing check did not complete (`{verify_error}`), "
            "but the file was written._"
        )
    context.emit_assistant_delta(reply)

    # Surface the artifact as a LinkPart ui_part; build_output forwards it on the
    # FinalRuntimeEvent so the chat renders an authenticated download chip.
    return StepResult(
        state_update={
            "final_text": reply,
            "done_reason": "files_complete",
            "link_parts": link_parts,
        }
    )


# ── Step: geo ──────────────────────────────────────────────────────────────────

_GEO_SAMPLE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [2.3522, 48.8566]},
            "properties": {"name": "Paris"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [13.4050, 52.5200]},
            "properties": {"name": "Berlin"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [2.33, 48.85],
                        [2.37, 48.85],
                        [2.37, 48.87],
                        [2.33, 48.87],
                        [2.33, 48.85],
                    ]
                ],
            },
            "properties": {"name": "Test zone", "color": "#6366f1", "fillOpacity": 0.2},
        },
    ],
}


@typed_node(TestState)
async def geo_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Emit a sample GeoJSON `FeatureCollection` as a `GeoPart` ui_part.

    Exercises the typed `GeoPart`/`ui_parts` rendering path (#1977's
    `GeoPartRenderer`, a static feature-count summary chip — the interactive
    Leaflet map was removed from the frontend, PR #2067, over a non-OSI
    dependency license) end to end, deterministically and without a real
    agent needing to call the `geo.render_points` builtin tool.

    SSE events exercised: status (x2), assistant_delta, final (with ui_parts).
    """
    delay = _delay_seconds(context)

    context.emit_status("geo", "Building a sample FeatureCollection.")
    await asyncio.sleep(0.05 + delay)
    context.emit_status("geo", "Sending map data.")

    reply = (
        "**Sample map.** Two pins (Paris, Berlin) and one styled polygon, "
        "sent as a `GeoPart` ui_part — rendered below as an interactive map, "
        "not as a markdown code block."
    )
    context.emit_assistant_delta(reply)

    geo_part = GeoPart(geojson=_GEO_SAMPLE, fit_bounds=True)

    return StepResult(
        state_update={
            "final_text": reply,
            "done_reason": "geo_complete",
            "geo_parts": [geo_part.model_dump(mode="json")],
        }
    )


# ── Step: document ────────────────────────────────────────────────────────────

_DOCUMENT_PROBE_QUESTION = "What is Fred?"


@typed_node(TestState)
async def document_step(
    state: TestState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Search documents through the `document_access` capability's
    `search_documents_using_vectorization` tool via `context.invoke_runtime_tool`
    (the Graph <-> AgentCapability bridge, NOTES-GRAPH-CAPABILITY-BRIDGE.md),
    then pause on a HITL choice to confirm or discard the top hit.

    Unlike `default_mcp_servers`, this tool is not declared on the agent
    class — `document_access` must be selected per-instance via
    `tuning.selected_capability_ids`. When it isn't, `invoke_runtime_tool`
    raises `RuntimeError('Runtime tool ... is not available.')`; this step
    catches that and degrades to a helpful final_text instead of crashing
    the node.

    Content: the text after the `document` keyword, or a built-in probe
    question when the user supplies none.

    SSE events exercised: status (x2), tool_call/tool_result (from
    invoke_runtime_tool), awaiting_human (choice), final (confirm/discard
    branch — sources attached only when confirmed).
    """
    delay = _delay_seconds(context)
    remainder = state.latest_user_text.strip()[len("document") :].strip()
    question = remainder or _DOCUMENT_PROBE_QUESTION

    context.emit_status("document", f"Searching documents for: {question}")
    await asyncio.sleep(0.05 + delay)

    try:
        result = await context.invoke_runtime_tool(
            "search_documents_using_vectorization",
            {"question": question, "top_k": 3},
        )
    except RuntimeError as exc:
        return StepResult(
            state_update={
                "final_text": (
                    "**Document search is unavailable on this agent instance.**\n\n"
                    'Enable the "Document access" capability on this instance '
                    "(`tuning.selected_capability_ids`), then try again.\n\n"
                    f"_Detail: {exc}_"
                ),
                "done_reason": "document_capability_unavailable",
            }
        )

    sources = result.get("sources") if isinstance(result, dict) else None
    hits = list(sources) if sources else []
    if not hits:
        return StepResult(
            state_update={
                "final_text": f"No documents matched: _{question}_.",
                "done_reason": "document_no_hits",
            }
        )

    top_hit = hits[0]
    title = top_hit.get("title", "untitled")
    score = top_hit.get("score", 0.0)
    content = top_hit.get("content", "")

    context.emit_status("document", "Awaiting confirmation of the top hit.")
    choice_id = await choice_step(
        context,
        stage="test_document_confirm",
        title="Test HITL — Confirm Document Result",
        question=(
            f"**Top hit:** {title} (score {score:.2f})\n\n{content}\n\n"
            "Keep this result, or discard it?"
        ),
        choices=[
            HumanChoiceOption(id="confirm", label="Confirm — keep this result"),
            HumanChoiceOption(id="discard", label="Discard — not relevant"),
        ],
    )

    if choice_id == "confirm":
        return StepResult(
            state_update={
                "sources_data": hits,
                "final_text": (
                    f"Document search confirmed. Keeping **{title}** as the answer source."
                ),
                "done_reason": "document_confirmed",
            }
        )
    if choice_id == "discard":
        return StepResult(
            state_update={
                "final_text": "Document search result discarded at your request.",
                "done_reason": "document_discarded",
            }
        )
    return StepResult(
        state_update={
            "final_text": "Document confirmation test: no selection received (None).",
            "done_reason": "document_none",
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
| `long` | 30-sentence word-by-word streaming reply |
| `files` | Unified `/fs` round-trip: write to the agent's space → read back → list directory |
| `geo` | Sample GeoJSON `FeatureCollection` rendered as a `GeoPart` ui_part (interactive map) |
| `document` | `document_access` capability tool call via `invoke_runtime_tool` + HITL confirm/discard gate on the top hit |"""


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
