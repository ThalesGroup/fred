# RFC: Agent Thinking API — Structured Chain-of-Thought for the Fred SDK

**ID:** RUNTIME-04  
**Author:** Dimitri Tombroff  
**Status:** Draft  
**Date:** 2026-05-23  
**Last amended:** 2026-07-22 — chat trace UI stops rendering the synthetic `tool_use` thought row (Amendment B)
**Track:** fred-sdk / fred-runtime execution contract

---

## 1. Problem

Agent authors have no structured way to expose reasoning to the chat UI.
The current surface provides only `emit_status(status, detail)` — a generic
progress ping — which the UI renders as an undifferentiated log line.

**What is missing:**

- A way to open a _reasoning block_, stream text into it, and close it — so
  the UI can render a collapsible "Thought" accordion with a phase label and
  accumulated reasoning text.
- A discriminator between reasoning phases (planning vs. tool reasoning vs.
  observation vs. reflection vs. synthesis) that the UI can use for visual
  treatment.
- A passthrough path so that native model thinking tokens (Anthropic extended
  thinking, Mistral adjustable reasoning chunks, and equivalent provider
  surfaces) arrive as the same event type as authored thoughts — a single UI
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
4. Specify what happens on models that have no native thinking (older Mistral
   variants and most open-weight models) — authored thoughts are the full story,
   nothing breaks.
5. Keep `emit_status` as a pure operational progress signal, unchanged.

---

## 3. Non-goals

- This RFC does not specify the frontend rendering of thought accordions (UX
  design is a separate track).
- This RFC does not add automatic thought extraction from LangGraph's internal
  callback events (`on_chain_start`, `on_tool_start`, etc.). Those are runtime
  plumbing; authored thoughts are business-level signals.
- Base RUNTIME-04 does not change the model provider adapter layer or LangChain
  configuration. RUNTIME-05 Layer 2b below covers the minimal stream-adapter
  work needed when providers already emit native thinking chunks.
- This RFC does not specify how `ReActAgent` tools surface thoughts (that is a
  follow-on if needed).

---

## 4. Model compatibility baseline

| Model family                              | Native thinking tokens                    | Authored thoughts | Notes                                                    |
| ----------------------------------------- | ----------------------------------------- | ----------------- | -------------------------------------------------------- |
| Mistral Small 4 / `mistral-small-latest`  | Yes — `ThinkChunk` / `TextChunk` when `reasoning_effort` is enabled | Yes | Runtime must split reasoning chunks from final text      |
| Older Mistral / Mistral without reasoning | No                                        | Yes — only source | Works fully via `context.thinking()`                     |
| Claude 3.7+ (extended thinking)           | Yes — `thinking` content blocks           | Yes               | Runtime intercepts blocks; maps to same events           |
| Claude 3.5 and below                      | No                                        | Yes               | Same as non-reasoning Mistral                            |
| OpenAI o1 / o3 / o4                       | Partial — `reasoning_content`             | Yes               | Runtime maps where available; graceful degradation        |
| GPT-4 / GPT-4o                            | No                                        | Yes               | Same as non-reasoning Mistral                            |
| Gemini 2.x                                | No                                        | Yes               | Same as non-reasoning Mistral                            |

**Key design consequence:** the authored path (`context.thinking()`) is the
primary path and must be fully self-sufficient. Model-native passthrough is an
additive enrichment layer, not a dependency. On deployments without provider
thinking support, the entire thinking surface works without any model
cooperation. On deployments where the provider does emit thinking chunks, those
chunks must be promoted to `THOUGHT_*` and suppressed from final answer text.

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

### 7.3 Mistral adjustable reasoning

Mistral Small 4 / `mistral-small-latest` can surface native reasoning when
`reasoning_effort` is enabled. In non-streaming responses, `message.content`
becomes a list containing:

- `ThinkChunk` (`type="thinking"`) with a nested `thinking` list of text chunks.
- `TextChunk` (`type="text"`) with the final answer.

Provider references: Mistral reasoning docs
(`https://docs.mistral.ai/studio-api/conversations/reasoning`) and Mistral
Small 4 model card
(`https://docs.mistral.ai/models/model-cards/mistral-small-4-0-26-03`).

In streaming responses, `delta.content` changes shape during the answer:

1. thinking phase — a list containing `ThinkChunk`
2. transition — a list containing a closing `ThinkChunk` and first `TextChunk`
3. answer phase — a plain string

The Fred runtime maps this to:

1. open one `ThoughtStartEvent(phase="planning", source="model_native", title="Model reasoning")`
   when the first thinking text fragment arrives
2. emit one `ThoughtDeltaEvent` per nested thinking text fragment
3. close the thought before emitting the first `TextChunk` or plain string answer
4. emit `TextChunk` and plain string content as normal `AssistantDeltaRuntimeEvent`

The first implementation should be permissive in the adapter: detect both SDK
objects and dict-shaped content blocks, because GCP/OpenAI-compatible gateways
may serialize provider chunks before LangChain receives them.

Important history rule: if Fred replays provider-native assistant messages back
to Mistral for multi-turn reasoning, it must preserve the provider's full
assistant message internally, including `ThinkChunk`. The UI-facing answer still
uses Fred `THOUGHT_*` plus final text; it must not display the raw chunk JSON as
assistant content.

### 7.4 All other models (GPT-4, Gemini, non-reasoning Mistral, etc.)

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
For Mistral reasoning-capable deployments, provider `ThinkChunk` content is first
normalized into Fred `THOUGHT_*` events and then bridged as `<think>` tags. For
models without native thinking, the `<think>` tags are authored by the agent via
`context.thinking()`. Open WebUI sees the same event shape in both cases.

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

| File                                  | Change                                                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `fred_sdk/contracts/runtime.py`       | Remove `thought_kind` from `StatusRuntimeEvent`; add three new event classes                                             |
| `fred_sdk/graph/runtime.py`           | Remove `thought_kind` from `emit_status` signature; add `thinking()` and `emit_thought()` to `GraphNodeContext` Protocol |
| `fred_runtime/graph/graph_runtime.py` | Implement `thinking()` context manager and `emit_thought()`; remove `thought_kind` from concrete `emit_status`           |
| `fred_sdk/__init__.py`                | Export new types; keep `ThoughtKind` (now used by new events, not `StatusRuntimeEvent`)                                  |
| `apps/fred-agents/.../graph_steps.py` | Rewrite `think_step` using `context.thinking()` and `emit_thought()`                                                     |

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
plumbing noise. The author decides _what_ to expose as reasoning, not the
framework. On models without extended thinking this approach produces zero
content anyway.

**D — Separate `ReasoningAgent` subclass**

Rejected. Thinking is a capability of the execution context, not an agent
subtype. Any graph node in any agent may emit thoughts. Making it a subclass
would require restructuring every existing agent to gain it.

---

## 14. Impact

| Component                             | Change                                                                                                                                                   |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fred_sdk/contracts/runtime.py`       | Add `ThoughtStartEvent`, `ThoughtDeltaEvent`, `ThoughtEndEvent`; remove `thought_kind` from `StatusRuntimeEvent`                                         |
| `fred_sdk/contracts/openai_compat.py` | Add `FredThoughtMeta`; extend `FredChunkMetadata` with `thought` field; map `THOUGHT_*` in `fred_event_to_openai_chunk`                                  |
| `fred_sdk/graph/runtime.py`           | Add `thinking()` context manager and `emit_thought()` to `GraphNodeContext` Protocol; remove `thought_kind` from `emit_status`                           |
| `fred_runtime/graph/graph_runtime.py` | Implement `thinking()` and `emit_thought()`; model-native passthrough for Anthropic extended thinking; remove `thought_kind` from concrete `emit_status` |
| `fred_sdk/__init__.py`                | Export new types: `ThoughtStartEvent`, `ThoughtDeltaEvent`, `ThoughtEndEvent`, `ThoughtRecord`, `ThoughtWriter`, `FredThoughtMeta`                       |
| `apps/fred-agents/.../graph_steps.py` | Rewrite `think_step` using `context.thinking()` / `emit_thought()`                                                                                       |
| OpenAPI / `runtimeOpenApi.ts`         | Regenerate — three new component schemas added                                                                                                           |
| Open WebUI                            | Zero config change — `<think>` tags render natively                                                                                                      |
| Fred chat UI                          | Optionally consume `fred.thought` for richer per-phase rendering                                                                                         |
| Evaluation harness                    | `thought_trace: tuple[ThoughtRecord, ...]` on `GraphExecutionOutput`                                                                                     |

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
   → **Resolved by Amendment A — RUNTIME-05** (see below).

---

## Amendment A — ReAct Thought Surface (RUNTIME-05)

**ID:** RUNTIME-05  
**Author:** Dimitri Tombroff  
**Status:** Draft  
**Date:** 2026-05-25  
**Amends:** RUNTIME-04 (open question 3)

### A.1 Problem

The `THOUGHT_*` event contract and the `context.thinking()` authoring API from
RUNTIME-04 are implemented for graph agents only, via `GraphNodeContext`.

ReAct agents (like Rico, `react_rag_mcp`) are pure declaration objects — a
system prompt and a tool list. There is no Python step handler where an author
could call `context.thinking()`. The only runtime events they emit today are
`tool_call`, `tool_result`, `assistant_delta`, `final`. The ThoughtTrace panel
is empty for all ReAct agents.

This is the wrong behaviour for two reasons:

1. **Template agents with MCP tools** (the most common case) will never have
   authored Python code. If the ThoughtTrace requires explicit author calls, it
   will always be empty for them.
2. **Every ReAct tool invocation** already has all the information needed for a
   `tool_use` + `observation` thought pair: tool name, arguments, result,
   latency. The runtime already holds this data and discards it.

Note: RUNTIME-04 §13 Alternative C (rejected) was "capture _all_ LangGraph
callback events automatically". That is not what this amendment proposes. We
target **tool call/result events only**, which are structured, meaningful,
model-agnostic, and already emitted by the runtime as `ToolCallRuntimeEvent` /
`ToolResultRuntimeEvent`. This is a targeted addition, not general callback
capture.

### A.2 Solution — two layers, independent and composable

#### Layer 1 — Runtime auto-synthesis (zero author code)

The `_TransportBackedReActExecutor.stream()` in `react_runtime.py` emits
`THOUGHT_START / THOUGHT_END` events bracketing every tool call/result pair:

```
THOUGHT_START(phase="tool_use",    title="Calling {tool_name}", thought_id=X)
TOOL_CALL(...)
TOOL_RESULT(...)
THOUGHT_END(thought_id=X, conclusion="{n_results} · {latency_ms}ms")
```

The `thought_id` is a fresh UUID per tool invocation, independent from the
`call_id` of the tool call. No `THOUGHT_DELTA` is emitted — these are
instantaneous structural thoughts, not streaming reasoning blocks.

This is implemented directly in the existing stream loop, not via LangChain
callbacks. The loop already detects `AIMessage` with `tool_calls` and
`ToolMessage`; wrapping those with `THOUGHT_*` emissions is additive and
model-agnostic.

**What the UI gains without any author action:**

| Before (today)                                        | After (Layer 1)                                        |
| ----------------------------------------------------- | ------------------------------------------------------ |
| Tool call row: `knowledge_search(query="X", top_k=5)` | Thought row: **Tool use** — "Calling knowledge_search" |
| Tool result row: `{"documents": [...], "score": ...}` | Conclusion: "3 results · 420ms"                        |

#### Layer 2 — Author-overridable thought configuration

Authors who want custom phase labels, titles, or conclusion templates override
one optional method on `ReActAgentDefinition`:

```python
class ReActAgentDefinition(AgentDefinition):
    ...
    def thought_config(
        self,
        tool_name: str,
        args: dict[str, object],
    ) -> "ReActThoughtConfig | None":
        """
        Return custom thought metadata for one tool invocation, or None for
        runtime defaults.

        Authors override this to replace the generic "Calling {tool_name}"
        label with a domain-specific title, or to suppress thoughts for
        specific tools entirely.

        Example:
            if tool_name == "knowledge_search":
                query = args.get("query", "")
                return ReActThoughtConfig(
                    phase="tool_use",
                    title=f"Searching: {query[:60]}",
                )
            if tool_name == "internal_health_check":
                return ReActThoughtConfig(suppress=True)
            return None
        """
        return None
```

```python
class ReActThoughtConfig(FrozenModel):
    phase: ThoughtKind = "tool_use"
    title: str | None = None          # None → runtime generates "Calling {tool_name}"
    conclusion_template: str | None = None  # None → runtime generates "{n} · {ms}ms"
    suppress: bool = False            # True → emit no thought for this tool call
```

The `_TransportBackedReActExecutor` calls `definition.thought_config(name, args)`
before emitting each `THOUGHT_START`. If the method returns `None` or the
definition does not override it, the runtime uses the defaults from Layer 1.

#### Why LangChain callbacks are NOT used for Layer 1

`BaseCallbackHandler.on_tool_start()` / `on_tool_end()` are correct LangChain
hooks. However:

- The stream loop already receives all tool events from LangGraph's `updates`
  stream — a second interception via callbacks would be redundant.
- Callbacks fire asynchronously relative to the SSE event queue; the stream loop
  is already the serialisation point.
- Callbacks can fire for internal LangGraph tools and chain nodes that are not
  agent-level tool calls — filtering would be necessary and fragile.
- The stream loop approach is consistent with how tool events are already handled
  in `react_runtime.py`.

LangChain callbacks remain available to authors who want to inject their own
observability or tracing via `adapter_config.callbacks`. They are not part of
the Fred thought emission path.

### A.3 Model-native thinking for ReAct (Layer 2b)

When a provider emits model-native reasoning inside `AIMessageChunk.content`, the
stream adapter must not pass the structured block through
`stringify_langchain_content()` as assistant text. That is the failure mode Simon
observed with Mistral reasoning enabled: the final answer can receive a large
JSON-like payload instead of a clean text delta plus thought trace.

In `react_stream_adapter.assistant_delta_from_stream_event()`:

- Detect `AIMessageChunk` where `content` is a list containing blocks of
  `type="thinking"` or provider SDK objects equivalent to Mistral `ThinkChunk`.
- Extract nested thinking text from Mistral `thinking[]` / Claude `text`-like
  fields and emit it through `THOUGHT_START(phase="planning",
  source="model_native", title="Model reasoning")`, `THOUGHT_DELTA`, and
  `THOUGHT_END`.
- Suppress thinking blocks from the assistant delta (they must not appear in the
  final answer text).
- Preserve `type="text"` blocks and plain strings as assistant deltas.
- Handle the Mistral transition frame where one streamed content list contains
  both the closing `ThinkChunk` and the first `TextChunk`: close the thought
  before emitting the first assistant text delta.

This is strictly additive. On models without native thinking, the code path is
not reached. On Claude or Mistral with reasoning disabled, the content is plain
text or text-only blocks and is unaffected.

### A.4 `ThoughtConfig` defaults

| Field                 | Default                                                                                |
| --------------------- | -------------------------------------------------------------------------------------- |
| `phase`               | `"tool_use"`                                                                           |
| `title`               | `"Calling {tool_name}"` (tool_name sanitised: underscores → spaces, title-cased)       |
| `conclusion_template` | `"{n_results} result(s) · {latency_ms}ms"` if `latency_ms` is available, else `"Done"` |
| `suppress`            | `False`                                                                                |

### A.5 Files changed

| File                                         | Change                                                                                                                                 |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `fred_sdk/contracts/models.py`               | Add `ReActThoughtConfig` model; add `thought_config()` to `ReActAgentDefinition`                                                       |
| `fred_runtime/react/react_runtime.py`        | Emit `THOUGHT_START/END` in `_TransportBackedReActExecutor.stream()` around tool call/result pairs; call `definition.thought_config()` |
| `fred_runtime/react/react_stream_adapter.py` | Detect and suppress native thinking blocks from `AIMessageChunk`; extract Mistral `ThinkChunk` / `TextChunk`; emit `THOUGHT_*` for `source="model_native"` |
| `fred_sdk/__init__.py`                       | Export `ReActThoughtConfig`                                                                                                            |
| `apps/fred-agents/fred_agents/rag_expert.py` | Optional: add `thought_config()` override for Rico demonstrating the API                                                               |

No changes to the SSE contract (`THOUGHT_*` event shapes are already defined in
RUNTIME-04). No changes to the frontend — the existing `useChatSse.ts` handler
already consumes `thought_start/delta/end` events.

### A.6 Alternatives considered

| Alternative                                                                            | Reason rejected                                                                                                                |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Auto-synthesise thoughts for ALL ReAct events (model calls, chain nodes)               | Too noisy — same reason as RUNTIME-04 §13 Alt C; tool calls are the only structured, meaningful surface                        |
| Add `context.thinking()` to ReAct via a `ToolContext` passed into tool implementations | Requires Fred to own the tool implementation; MCP tools and LangChain tools are third-party code — no injection point          |
| No auto-synthesis; require all ReAct authors to subclass and override                  | Template agents (no Python code) would always have empty ThoughtTrace; the whole feature is unusable for the dominant use case |

---

## Amendment B — Drop the synthetic `tool_use` thought row from the UI; carry latency on the tool-result event instead (2026-07-22)

**Author:** Dimitri Tombroff
**Date:** 2026-07-22
**Amends:** RUNTIME-04 / Amendment A (Layer 1 auto-synthesis)

### B.1 Problem

Amendment A (§A.2, Layer 1) specified that the runtime auto-synthesize a
`tool_use` thought around every tool call, closed with
`conclusion="{n_results} · {latency_ms}ms"` — e.g. "3 results · 420ms". The
implementation in `react_runtime.py` never built that template; it closes
every `tool_use` thought with the hardcoded literal `conclusion="Error" if
is_error else "Done"`. In the chat UI, this produced one **"Tool use" / Done**
row per tool call, in addition to the `tool_call`/`tool_result` combo row that
already shows the humanized tool label and status — a redundant, content-free
row repeated once per tool invocation (user-reported, chain-of-thought
review, 2026-07-22).

### B.2 Decision

Rather than implementing the original `"{n_results} · {latency_ms}ms"`
template (which requires a per-tool-shape result digest — fragile and
tool-specific to generalize) the fix moves the one piece of that template that
*is* generic — latency — onto the `ToolResultRuntimeEvent` itself
(`latency_ms: int | None`, populated from the same
`_elapsed_ms_since(thought_started_at)` call already computed for the
`ThoughtEndEvent`), and the frontend (`traceUtils.groupTraceEntries()`) stops
rendering the `tool_use`-phase solo thought row entirely — see
`RUNTIME-EXECUTION-CONTRACT.md` §8.21 for the full change.

The backend still emits the `ThoughtStartEvent(phase="tool_use")` /
`ThoughtEndEvent(conclusion="Done"/"Error")` pair unchanged (no behavior change
for any other consumer, e.g. eval trace/replay tooling that reads the full
event stream) — only the chat UI's trace list stops rendering that specific
row, because the paired combo row now conveys the same "what ran, how it went,
how long it took" information on its own.

This does not fully satisfy Amendment A's original template — there is no
"3 results" style count in the UI today. That remains a legitimate fast-follow
if a specific need for it shows up, implemented as a per-tool `thought_config()`
override (Layer 2, §A.2) rather than a generic runtime digest, since result
shape is tool-specific and Layer 2 already exists for exactly this purpose.

Non-`tool_use` thought phases (`planning`, `observation`, `reflection`,
`synthesis`) are unaffected — their `conclusion` is real agent-authored or
model-native text, not this synthetic placeholder, and continues to render.
