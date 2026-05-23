# RFC: Agent Thinking API — Structured Chain-of-Thought for the Fred SDK

**ID:** RUNTIME-04  
**Author:** Dimitri Tombroff  
**Status:** Draft  
**Date:** 2026-05-23  
**Track:** fred-sdk / fred-runtime execution contract

---

## 1. Problem

Agent authors have no structured way to expose reasoning to the chat UI.
The current surface provides only `emit_status(status, detail)` — a generic
progress ping — which the UI renders as an undifferentiated log line.

**What is missing:**

- A way to open a *reasoning block*, stream text into it, and close it — so
  the UI can render a collapsible "Thought" accordion with a phase label and
  accumulated reasoning text.
- A discriminator between reasoning phases (planning vs. tool reasoning vs.
  observation vs. reflection vs. synthesis) that the UI can use for visual
  treatment.
- A passthrough path so that native model thinking tokens (Anthropic extended
  thinking) arrive as the same event type as authored thoughts — a single UI
  component handles all sources.
- A durable record of the reasoning trace attached to `GraphExecutionOutput`
  for evaluation and replay.

**Why `thought_kind` on `StatusRuntimeEvent` is the wrong fix:**

It turns a progress signal into a makeshift thought carrier.
`STATUS` events are fire-and-forget pings. They have no open/close semantics,
no accumulated text body, no correlation ID. Piggybacking phase metadata onto
them cannot produce the open/close model the UI needs for a streaming accordion.
That field must be reverted and replaced by the design below.

---

## 2. Goals

1. Give agent authors a clean, model-agnostic authoring primitive to express
   reasoning phases as streaming blocks.
2. Define a minimal set of new SSE event types with proper open/close semantics.
3. Specify how native model thinking tokens (where available) are mapped to the
   same event types so the UI consumes one contract regardless of the model.
4. Specify what happens on models that have no native thinking (Mistral and most
   open-weight models) — authored thoughts are the full story, nothing breaks.
5. Keep `emit_status` as a pure operational progress signal, unchanged.

---

## 3. Non-goals

- This RFC does not specify the frontend rendering of thought accordions (UX
  design is a separate track).
- This RFC does not add automatic thought extraction from LangGraph's internal
  callback events (`on_chain_start`, `on_tool_start`, etc.). Those are runtime
  plumbing; authored thoughts are business-level signals.
- This RFC does not change the model provider adapter layer or LangChain
  configuration — only the SSE contract surface and the authoring API.
- This RFC does not specify how `ReActAgent` tools surface thoughts (that is a
  follow-on if needed).

---

## 4. Model compatibility baseline

| Model family | Native thinking tokens | Authored thoughts | Notes |
|---|---|---|---|
| Mistral (all) | No | Yes — only source | Primary target; works fully via `context.thinking()` |
| Claude 3.7+ (extended thinking) | Yes — `thinking` content blocks | Yes | Runtime intercepts blocks; maps to same events |
| Claude 3.5 and below | No | Yes | Same as Mistral |
| OpenAI o1 / o3 / o4 | Partial — `reasoning_content` | Yes | Runtime maps where available; graceful degradation |
| GPT-4 / GPT-4o | No | Yes | Same as Mistral |
| Gemini 2.x | No | Yes | Same as Mistral |

**Key design consequence:** the authored path (`context.thinking()`) is the
primary path and must be fully self-sufficient. Model-native passthrough is an
additive enrichment layer, not a dependency. On Mistral-only deployments, the
entire thinking surface works without any model cooperation.

---

## 5. New SSE event types

Three new `RuntimeEventKind` values are added:

```
THOUGHT_START   — opens a reasoning block
THOUGHT_DELTA   — streams text into an open block
THOUGHT_END     — closes a reasoning block
```

### 5.1 `ThoughtKind` (phase discriminator)

```python
ThoughtKind = Literal[
    "planning",     # deciding what to do / which tools to call
    "tool_use",     # reasoning immediately before or after a tool invocation
    "observation",  # interpreting a tool result
    "reflection",   # self-correction or re-planning after an observation
    "synthesis",    # assembling the final answer from collected evidence
]
```

`ThoughtKind` is exported from `fred_sdk` for use by agent authors.

### 5.2 `ThoughtStartEvent`

```python
class ThoughtStartEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.THOUGHT_START] = RuntimeEventKind.THOUGHT_START
    thought_id: str          # UUID — correlation key for DELTA and END
    phase: ThoughtKind
    title: str | None = None # optional short user-facing label
    source: Literal["authored", "model_native"] = "authored"
```

### 5.3 `ThoughtDeltaEvent`

```python
class ThoughtDeltaEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.THOUGHT_DELTA] = RuntimeEventKind.THOUGHT_DELTA
    thought_id: str   # matches the opening THOUGHT_START
    delta: str        # incremental text fragment
```

### 5.4 `ThoughtEndEvent`

```python
class ThoughtEndEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.THOUGHT_END] = RuntimeEventKind.THOUGHT_END
    thought_id: str
    conclusion: str | None = None   # optional one-line summary of what was concluded
    duration_ms: int | None = None  # wall-clock time of the block in ms
```

### 5.5 What `emit_status` reverts to

`StatusRuntimeEvent` loses the `thought_kind` field added in the previous
session. It stays as a pure operational progress signal with no reasoning
semantics:

```python
class StatusRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.STATUS] = RuntimeEventKind.STATUS
    status: str = Field(..., min_length=1)
    detail: str | None = None
    # thought_kind removed — reasoning uses THOUGHT_START/DELTA/END
```

---

## 6. Authoring API

### 6.1 `GraphNodeContext.thinking()` — context manager (primary API)

```python
async def thinking(
    self,
    phase: ThoughtKind,
    *,
    title: str | None = None,
) -> AsyncContextManager[ThoughtWriter]:
    ...
```

On `__aenter__`: emits `ThoughtStartEvent` with a fresh UUID and starts a
wall-clock timer.

On `__aexit__`: emits `ThoughtEndEvent` with accumulated `duration_ms`.
If the block body raised an exception the event is still emitted (no leaked
open blocks).

**Usage:**

```python
async with context.thinking("planning", title="Deciding which tools to call") as thought:
    await thought.write("The user is asking about X. Relevant tools: Y, Z.")
    await thought.write("Y covers structured data; I will call it first.")
```

### 6.2 `ThoughtWriter` protocol

```python
class ThoughtWriter(Protocol):
    async def write(self, text: str) -> None:
        """Emit one THOUGHT_DELTA for this block."""
        ...

    async def conclude(self, text: str) -> None:
        """Set the conclusion text that will appear in THOUGHT_END."""
        ...
```

`write()` may be called any number of times. Callers can chunk text freely —
one call per sentence, one per paragraph, one for the whole block — depending
on how much streaming granularity they want in the UI.

`conclude()` is optional. If omitted, `ThoughtEndEvent.conclusion` is `None`.

### 6.3 `GraphNodeContext.emit_thought()` — convenience (non-streaming)

For cases where the entire reasoning text is known upfront and streaming
granularity is not needed:

```python
def emit_thought(
    self,
    phase: ThoughtKind,
    text: str,
    *,
    title: str | None = None,
    conclusion: str | None = None,
) -> None:
    """Emit START + single DELTA + END in one synchronous call."""
    ...
```

This is the correct replacement for the current `emit_status(..., thought_kind=...)` pattern.

---

## 7. Model-native passthrough

### 7.1 Anthropic extended thinking

When the model response contains `thinking` content blocks, the graph runtime
intercepts them during streaming and emits:

1. `ThoughtStartEvent(phase="synthesis", source="model_native", title="Model reasoning")`
2. One `ThoughtDeltaEvent` per streamed thinking token chunk
3. `ThoughtEndEvent` when the block closes

The agent author does not need to do anything. If the author also calls
`context.thinking()` in the same node, both streams appear as separate thought
blocks with distinct `thought_id` values.

### 7.2 OpenAI reasoning models (o1 / o3 / o4)

Where the API exposes `reasoning_content` in the streamed response, the same
mapping applies with `source="model_native"`. Where it is not exposed (o1 early
versions hide it), nothing is emitted — graceful silence.

### 7.3 All other models (Mistral, GPT-4, Gemini, etc.)

No passthrough. `source="authored"` thoughts from `context.thinking()` are the
only source. The UI sees a consistent stream of `THOUGHT_*` events regardless.

---

## 8. Durable trace — `ThoughtRecord` and `GraphExecutionOutput`

### 8.1 `ThoughtRecord`

A frozen, serialisable record of one completed reasoning block:

```python
class ThoughtRecord(FrozenModel):
    thought_id: str
    phase: ThoughtKind
    title: str | None
    text: str             # full accumulated text (all deltas concatenated)
    conclusion: str | None
    duration_ms: int | None
    source: Literal["authored", "model_native"]
```

### 8.2 `GraphExecutionOutput` extension

```python
class GraphExecutionOutput(FrozenModel):
    content: str = ""
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    thought_trace: tuple[ThoughtRecord, ...] = ()   # NEW
```

The runtime assembles `thought_trace` from all completed blocks during the run.
Agent authors do not populate it manually — it is built from the `THOUGHT_END`
events automatically. It is available for evaluation harnesses and session
history replay.

---

## 9. OpenAI-compatible bridge — Open WebUI compliance

Fred exposes `/v1/chat/completions` via `openai_compat_router.py`. This endpoint
is the primary integration point for Open WebUI. The transformer function
`fred_event_to_openai_chunk` currently drops all unknown event kinds, which means
`THOUGHT_*` events would be silently discarded without this section.

### 9.1 De-facto standard: `<think>` tags

The industry standard for thinking content in OpenAI-compatible streams — used
by DeepSeek R1, QwQ, Mistral reasoning variants, and rendered natively by Open
WebUI without any plugin or configuration — is `<think>...</think>` tags
embedded in the `content` delta field.

Open WebUI detects the opening tag, opens a collapsible "Thought" accordion,
streams content into it, and closes it on the closing tag. The subsequent
content stream is rendered as the normal answer. This works on every model
family, including Mistral deployments.

### 9.2 Mapping `THOUGHT_*` events to OpenAI chunks

```
THOUGHT_START  →  delta.content = "<think>"
                  fred.thought  = { thought_id, phase, title, event="start" }

THOUGHT_DELTA  →  delta.content = <the reasoning text fragment>
                  fred.thought  = { thought_id, event="delta" }

THOUGHT_END    →  delta.content = "</think>"
                  fred.thought  = { thought_id, event="end",
                                    conclusion, duration_ms }
```

`STATUS` events continue to be dropped. All other mappings are unchanged.

### 9.3 `FredChunkMetadata` extension

```python
class FredThoughtMeta(BaseModel):
    thought_id: str
    phase: str | None = None         # ThoughtKind value
    title: str | None = None
    event: Literal["start", "delta", "end"]
    conclusion: str | None = None    # only on end
    duration_ms: int | None = None   # only on end
    source: Literal["authored", "model_native"] = "authored"

class FredChunkMetadata(BaseModel):
    sources: list[FredSourceRef] = Field(default_factory=list)
    awaiting_human: HumanInputRequest | None = None
    node_error: str | None = None
    token_usage: dict[str, int] | None = None
    ui_parts: list[UiPart] = Field(default_factory=list)
    thought: FredThoughtMeta | None = None   # NEW
```

### 9.4 Why this design

**Standard clients (Open WebUI, openai-python SDK, etc.):**
The `content` delta stream contains `<think>...</think>` which Open WebUI renders
natively. No Fred-specific configuration needed.

**Fred-aware clients (Fred chat UI):**
The `fred.thought` field carries the full structured metadata — phase, title,
duration, conclusion, source — enabling richer visual treatment (phase icons,
colour coding, timing badges) beyond what `<think>` tags alone convey. Fred UI
can ignore the `<think>` tags and drive its accordion entirely from `fred.thought`.

**Mistral and models without native thinking:**
Works identically. The `<think>` tags are authored by the agent via
`context.thinking()`, not generated by the model. Open WebUI sees exactly the
same event shape regardless of the underlying model.

### 9.5 Stream ordering guarantee

Within one reasoning block the sequence is always:

```
THOUGHT_START → (1..N) THOUGHT_DELTA → THOUGHT_END
```

Multiple blocks may be interleaved with `ASSISTANT_DELTA` events between them
(e.g. a `synthesis` block immediately before the answer text). The `thought_id`
correlation key allows the UI to close one accordion and begin another without
ambiguity.

---

## 11. Migration: revert `thought_kind` on `StatusRuntimeEvent`

The `thought_kind: ThoughtKind | None` field added to `StatusRuntimeEvent` in
the previous session must be removed as part of implementing this RFC.

**Migration surface:**

| File | Change |
|---|---|
| `fred_sdk/contracts/runtime.py` | Remove `thought_kind` from `StatusRuntimeEvent`; add three new event classes |
| `fred_sdk/graph/runtime.py` | Remove `thought_kind` from `emit_status` signature; add `thinking()` and `emit_thought()` to `GraphNodeContext` Protocol |
| `fred_runtime/graph/graph_runtime.py` | Implement `thinking()` context manager and `emit_thought()`; remove `thought_kind` from concrete `emit_status` |
| `fred_sdk/__init__.py` | Export new types; keep `ThoughtKind` (now used by new events, not `StatusRuntimeEvent`) |
| `apps/fred-agents/.../graph_steps.py` | Rewrite `think_step` using `context.thinking()` and `emit_thought()` |

The `ThoughtKind` Literal itself is kept — it becomes the `phase` field on the
new events. Only its attachment to `StatusRuntimeEvent` is removed.

---

## 12. Runtime event kind additions (full updated list)

The `RuntimeEventKind` enum gains three values:

```python
class RuntimeEventKind(str, Enum):
    STATUS          = "status"
    TOOL_CALL       = "tool_call"
    TOOL_RESULT     = "tool_result"
    THOUGHT_START   = "thought_start"   # NEW
    THOUGHT_DELTA   = "thought_delta"   # NEW
    THOUGHT_END     = "thought_end"     # NEW
    AWAITING_HUMAN  = "awaiting_human"
    ASSISTANT_DELTA = "assistant_delta"
    NODE_ERROR      = "node_error"
    FINAL           = "final"
    TURN_PERSISTED  = "turn_persisted"
    EXECUTION_ERROR = "execution_error"
```

The `RuntimeEvent` union is extended to include `ThoughtStartEvent`,
`ThoughtDeltaEvent`, `ThoughtEndEvent`.

---

## 13. Alternatives considered

**A — Keep `thought_kind` on `StatusRuntimeEvent`**

Rejected. `STATUS` is a fire-and-forget progress ping. Adding phase metadata
to it produces an event that is semantically two different things. It cannot
represent streaming reasoning text, cannot correlate open/close, and leaves the
UI unable to render an accordion. It is a local fix that forecloses the real
solution.

**B — A single `ThoughtEvent` with a `subkind` field (start | delta | end)**

Rejected. A three-value discriminated union of concrete event types is more
idiomatic in the existing contract (every other event kind is a separate class)
and easier for typed frontend consumers to dispatch on without runtime checks.

**C — Capture all LangGraph callback events automatically (no authored API)**

Rejected. LangGraph's `on_chain_start`, `on_tool_start`, etc. are implementation
events, not business reasoning. Auto-capturing them floods the UI with internal
plumbing noise. The author decides *what* to expose as reasoning, not the
framework. On models without extended thinking this approach produces zero
content anyway.

**D — Separate `ReasoningAgent` subclass**

Rejected. Thinking is a capability of the execution context, not an agent
subtype. Any graph node in any agent may emit thoughts. Making it a subclass
would require restructuring every existing agent to gain it.

---

## 14. Impact

| Component | Change |
|---|---|
| `fred_sdk/contracts/runtime.py` | Add `ThoughtStartEvent`, `ThoughtDeltaEvent`, `ThoughtEndEvent`; remove `thought_kind` from `StatusRuntimeEvent` |
| `fred_sdk/contracts/openai_compat.py` | Add `FredThoughtMeta`; extend `FredChunkMetadata` with `thought` field; map `THOUGHT_*` in `fred_event_to_openai_chunk` |
| `fred_sdk/graph/runtime.py` | Add `thinking()` context manager and `emit_thought()` to `GraphNodeContext` Protocol; remove `thought_kind` from `emit_status` |
| `fred_runtime/graph/graph_runtime.py` | Implement `thinking()` and `emit_thought()`; model-native passthrough for Anthropic extended thinking; remove `thought_kind` from concrete `emit_status` |
| `fred_sdk/__init__.py` | Export new types: `ThoughtStartEvent`, `ThoughtDeltaEvent`, `ThoughtEndEvent`, `ThoughtRecord`, `ThoughtWriter`, `FredThoughtMeta` |
| `apps/fred-agents/.../graph_steps.py` | Rewrite `think_step` using `context.thinking()` / `emit_thought()` |
| OpenAPI / `runtimeOpenApi.ts` | Regenerate — three new component schemas added |
| Open WebUI | Zero config change — `<think>` tags render natively |
| Fred chat UI | Optionally consume `fred.thought` for richer per-phase rendering |
| Evaluation harness | `thought_trace: tuple[ThoughtRecord, ...]` on `GraphExecutionOutput` |

---

## 16. Open questions

1. **Nesting:** Should a `planning` block be allowed to contain a nested
   `tool_use` block? The current design is flat (parallel blocks, separate
   `thought_id` values). Nesting could be added later via an optional
   `parent_thought_id` field without breaking the existing contract.

2. **`TOOL_CALL` / `TOOL_RESULT` correlation:** Should `THOUGHT_DELTA` events
   inside a `tool_use` block be correlated with the `TOOL_CALL` event that
   follows? The current design leaves this as a convention (emit the `tool_use`
   thought immediately before the tool call). A formal `tool_call_id` reference
   could be added later.

3. **ReAct agent surface:** This RFC covers `GraphNodeContext` only. If ReAct
   agents need to emit thoughts from tool implementations, a follow-on RFC
   covering `ToolContext` is needed.
