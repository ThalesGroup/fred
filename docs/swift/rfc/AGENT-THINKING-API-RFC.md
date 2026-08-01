# RFC: Agent Thinking API — Structured Chain-of-Thought for the Fred SDK

**ID:** RUNTIME-04  
**Author:** Dimitri Tombroff  
**Status:** Draft  
**Date:** 2026-05-23  
**Last amended:** 2026-07-30 — trace presentation split into a reasoning lane and a numbered tool-step lane; collapse behaviour fixed (Amendment D)
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

> **Verified against the live API on 2026-07-29 — see Amendment C.** The wire
> format below is confirmed exactly as specified; Amendment C §C.2 records the
> observed payload verbatim and adds two details this section did not capture
> (the `closed` flag, and the absence of any top-level `reasoning_content`).

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

---

## Amendment C — Reasoning continuity across the tool loop: measured findings (2026-07-29)

**Author:** Timothé Le Chatelier
**Date:** 2026-07-29
**Status:** Measured findings. Confirms §7.3 and §A.3; identifies one scope gap
in this RFC and one undocumented load-bearing dependency in the runtime. No
design change is proposed here — see §C.8 for the decisions this enables.
**Amends:** §7.3 (Mistral adjustable reasoning), §A.3 (Layer 2b)
**Related:** `docs/swift/issues/ISSUE-005-reasoning-model-redundant-tool-calls.md`

### C.1 Why this amendment exists

ISSUE-005 documented, from a reported observation, that enabling
`reasoning_effort` on a tool-calling ReAct agent makes the model re-issue the
same tool call 3–5 times per turn. Its §7 step 1 — "reproduce and capture a
clean trace as the regression fixture" — was never done, and no trace exists in
the repository. Every downstream recommendation in that issue (including a 3–5
engineer-day client migration) therefore rested on an unverified premise.

This amendment records a measurement campaign run against the live Mistral API
on 2026-07-28/29 (147 trials across two benches plus three structural probes),
which confirms the core claim, refutes two of its supporting premises, and
identifies why the symptom is not currently visible in production.

**Scope of the evidence.** One model (`mistral-small-latest`,
`reasoning_effort: high`, temperature 0), one question, one to two tools,
`langchain-openai 1.3.2`, repository at `c170333d`. Sufficient to establish
causal direction and order of magnitude; insufficient to generalise to other
providers or to multi-tool chains of arbitrary depth.

### C.2 Confirmed — the Mistral wire format (amends §7.3)

The observed non-streaming payload, verbatim:

```json
{
  "role": "assistant",
  "tool_calls": [{ "id": "PGYQU5Tiw", "type": "function", "function": { ... } }],
  "content": [
    {
      "type": "thinking",
      "thinking": [{ "type": "text", "text": "L'utilisateur demande le délai…" }],
      "closed": true
    }
  ]
}
```

Two details §7.3 did not capture:

- Each `ThinkChunk` carries a `closed: boolean` flag.
- There is **no top-level `reasoning_content` field**. The reasoning travels
  exclusively as a `content` block. This matters for §C.3.

`support/thinking.py` already duck-types this shape correctly; no change needed.

### C.3 Refuted — "the client cannot carry the reasoning"

`ChatOpenAI` is documented (`base.py:1-11`) as not extracting non-standard
third-party fields such as `reasoning_content`. That warning was read as meaning
Fred never receives Mistral's reasoning. **That reading is wrong.** Because
Mistral ships the reasoning as an ordinary `content` block (§C.2) and not as an
exotic top-level field, LangChain passes it through untouched.

Probe, against the live endpoint through `ChatOpenAI` + `bind_tools`:

```text
type(content)     : list
types de blocs    : ['thinking']
tool_calls        : ['knowledge_search']
>>> reasoning received by Fred : True
```

The reasoning therefore _does_ reach the checkpoint, and
`strip_reasoning_from_history` genuinely has material to remove. §A.3 (Layer 2b)
is correct as specified and is the reason the UI shows
`PLANNING · Model reasoning`.

### C.4 The real blocker is the outbound direction

`_format_message_content` (`langchain_openai/chat_models/base.py:296-306`) drops
`thinking` and `reasoning_content` blocks from any message it sends, under the
comment "Remove unexpected block types". Probe:

| target API         | `thinking` block preserved on send |
| ------------------ | ---------------------------------- |
| `chat/completions` | **No**                             |
| `responses`        | **No**                             |

Consequence, and the single most actionable finding of this campaign: **removing
Fred's own strip achieves nothing**, because the client re-applies an equivalent
filter one layer down. Measured on the real stack, 10 trials per condition:

| condition                                           | turns with a duplicate | duplicate calls |
| --------------------------------------------------- | ---------------------- | --------------- |
| `mistral-medium` (historical default, no reasoning) | 0 / 10                 | 0               |
| `mistral-small`, reasoning **off**                  | 0 / 10                 | 0               |
| `mistral-small` + reasoning, **with** Fred's strip  | 10 / 10                | 28              |
| `mistral-small` + reasoning, **strip removed**      | 10 / 10                | 28              |

The bare-loop rate was re-measured twice more under the same conditions
(16/16 → 40 duplicates; 12/12 → 30), so the effect is stable, not a one-off.

Any fix must therefore replace or bypass the model client. Amending Fred alone
cannot work. This is the empirical basis for ISSUE-005 §6, and it narrows the
target: the defect is entirely in the model-access layer, not in Fred's
orchestration.

### C.5 Not reproduced — the HTTP 422 that justifies stripping

`support/thinking.py:185-201` justifies `strip_reasoning_from_history` by
stating that Mistral rejects replayed assistant content with
`HTTP 422 ("content … should be a valid string")`.

**17 trials replaying the raw `thinking` block verbatim produced zero
rejections.** The current API accepts the shape the docstring describes as
refused. The documented justification for the strip is not currently valid.

This does not by itself unblock anything — §C.4 shows the client filters
regardless — but it removes the 422 from the set of hard constraints, and it
should be re-verified rather than assumed by anyone designing the fix.

_Caveat:_ one model, one scenario, one API generation. Sufficient to demote the
422 from certainty to open question; insufficient to declare it extinct.

### C.6 Validated — threading the reasoning does fix it

Measured on a raw-HTTP bench where threading is actually possible (bypassing the
§C.4 filter), replaying the `thinking` block verbatim inside the open tool loop:

| condition                        | turns with a duplicate | duplicate calls |
| -------------------------------- | ---------------------- | --------------- |
| reasoning disabled               | 0 / 5                  | 0               |
| reasoning + strip (Fred's model) | 8 / 17 (47 %)          | 10              |
| reasoning + verbatim replay      | 2 / 17 (12 %)          | 2               |

One-sided Fisher exact test on the 12-trial sub-campaign (6/12 vs 1/12):
**p = 0.034**.

The "thread within the open turn, strip on closed turns" rule that ISSUE-005 §6.3
proposes is therefore validated experimentally, not merely by analogy with other
frameworks.

_Method note, recorded because it nearly caused a wrong conclusion:_ at n = 5 the
contrast was 2/5 vs 1/5 and the interim reading was "threading changes nothing".
That was underpowering, not a result. Twelve trials per condition were needed for
the signal to separate.

### C.7 The symptom is currently masked by an unrelated prompt suffix

Despite every link of the mechanism being armed in production — reasoning active,
`CheckpointHygieneMiddleware` outermost in the ReAct frame
(`middleware/frame.py:79`), no guardrail configured — duplicate tool calls are
**not observed** in the running product, including against an empty corpus where
retrieval returns nothing useful.

The reason is `build_tool_failure_recovery_suffix()`
(`react/react_prompting.py:219-226`), added by commit `d2f1c467` for issue #2073
(agents surfacing raw tool-error text as the final answer). It instructs the
model to "retry the call **with corrected arguments**" and to "answer from what
other calls have **already returned** if that is enough". Both clauses function
as anti-repetition guidance, and it is injected at composition time so it
survives an operator replacing the agent prompt wholesale.

Its effect is large. Identical conditions, 12 trials per prompt:

| system prompt                        | turns with a duplicate | duplicate calls |
| ------------------------------------ | ---------------------- | --------------- |
| none                                 | 12 / 12                | 30              |
| generic, role-only                   | 12 / 12                | **41**          |
| explicit anti-repetition instruction | **0 / 12**             | **0**           |

Note that a generic prompt provides no protection at all — marginally worse than
none. Only the explicit instruction suppresses the behaviour.

**This is a load-bearing dependency that nobody has written down.** The suffix was
authored for a different problem; no test, comment, or document ties it to
reasoning-drift suppression. Reformulating it for #2073 reasons would silently
re-expose the defect, with nothing to catch the regression. Recording that
coupling is the cheapest risk reduction available here.

### C.8 Runtime guardrail state, as measured and read

Verified against the code at `c170333d`, correcting an earlier assertion that no
guardrail existed:

| element                  | state                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Per-turn iteration cap   | **Implemented.** `ToolCallLimitMiddleware` wired at `middleware/frame.py:114-126`, placed after `FredHitl` so `after_model`'s reverse ordering blocks over-limit calls before the human gate.                                                                                                                                                         |
| … but active?            | **No.** Appended only when `max_tool_calls_per_turn` is set; default `None`, and no agent config in `apps/` sets it.                                                                                                                                                                                                                                  |
| Tool-call de-duplication | **Absent.** No hashing of `(tool_name, canonical_args)` anywhere in `react/` or `support/`. Existing dedup covers tool _names_ at assembly time only.                                                                                                                                                                                                 |
| `allow_parallel_calls`   | **Decorative.** Never reaches the model; its only production use renders a sentence into a prompt summary (`fred_sdk/contracts/models.py:1262`).                                                                                                                                                                                                      |
| SDK contract docstring   | **Stale.** `ToolSelectionPolicy` still says the cap is "Reserved for now … does not enforce this limit yet" (`models.py:797, 810-811`), which has been untrue since `frame.py` wired it. A reader would conclude the only available lever is inoperative.                                                                                             |
| Chat UI trace rendering  | **Not hiding anything.** `traceUtils.groupTraceEntries()` filters only `tool_use`-phase thought rows (Amendment B) and de-duplicates `tool_call` messages **by `call_id`**; genuinely repeated calls carry distinct provider ids and render separately. `runtime.py:183` enforces `call_id` non-empty, so the `!id` drop branch is unreachable today. |

### C.9 Scope gap in this RFC

This RFC — including Amendment A — specifies how model-native reasoning is
**surfaced**: detected, split from the answer, streamed as `THOUGHT_*`, and kept
out of the assistant text. It works, and §C.3 confirms it end to end.

It has never specified what happens to that reasoning on the **way back into the
model**. Continuity across an open tool loop is out of scope of every section
written so far, and `strip_reasoning_from_history` was introduced as runtime
hygiene rather than as a decision this RFC recorded. §C.4 shows that gap has a
measurable behavioural cost.

Two coherent resolutions, both requiring a decision this amendment does not take:

1. Declare reasoning continuity an explicit **non-goal** of this RFC and move it
   wholly to ISSUE-005 / its successor RFC, with a pointer from §7 so the
   boundary is visible to the next reader.
2. Extend this RFC with a "Layer 2c — reasoning continuity" section stating the
   thread-within-open-turn rule (ISSUE-005 §6.3) as part of the thinking
   contract, since the same content is at stake in both directions.

### C.10 Open questions this campaign raises

1. **Is the 422 genuinely gone, or shape-dependent?** §C.5 tested one replay
   shape on one API generation. Before any design relies on being able to replay
   reasoning, the accepted shapes should be enumerated deliberately.
2. **Does `use_previous_response_id` work against Mistral?** `base.py:3003-3006`
   suggests `use_responses_api=True, use_previous_response_id=True` for
   non-OpenAI endpoints reached via `base_url`, which would offload continuity to
   the provider. §C.4 shows the block filter applies to the `responses` API too,
   so the entire hope rests on the previous-response-id semantics being
   implemented server-side. A one-hour spike settles it, and settling it first
   may remove the need for a multi-day client migration.
3. **Does the §C.7 masking hold for single-tool agents?** The production agent
   observed uses the multi-tool `document_access` capability. A capability
   exposing one dominant tool has not been tested against the real prompt stack.
4. **Should the anti-repetition guidance be made explicit and tested?** Adding it
   to `build_runtime_tool_prompt_suffix()` (`react_tool_binding.py:98-105`) —
   which currently carries no such rule — would make the protection intentional
   and greppable rather than incidental to #2073.

### C.11 Reproducing these measurements

The campaign harnesses are not committed (they hold no repository-relevant code
and require a live API key). Their shape, for anyone re-running:

| harness           | what it establishes                                                                                                                     | key needed |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| mechanism proof   | Imports the real `strip_reasoning_from_history`; asserts the replayed assistant `content` collapses to `''` while `tool_calls` survive. | no         |
| wire-format dump  | Prints the raw Mistral message with `reasoning_effort` enabled (§C.2).                                                                  | yes        |
| bench A           | Raw HTTP, strip vs verbatim replay, duplicate signature counting (§C.6).                                                                | yes        |
| structural probes | Reasoning traversal through `ChatOpenAI`, inbound and outbound (§C.3, §C.4).                                                            | yes        |
| bench B           | Real stack, `ChatOpenAI` + the real strip, with and without it (§C.4).                                                                  | yes        |
| prompt control    | Identical conditions, three system prompts (§C.7).                                                                                      | yes        |

A duplicate is counted as a tool call whose
`(name, JSON-canonicalised sorted arguments)` signature already appeared in the
same turn. Tool results are held constant across a run so that no new information
can legitimately justify a second call.

---

## Amendment D — Trace presentation: reasoning is not a tool step (2026-07-30)

**ID:** #2172
**Status:** Implemented (frontend only)
**Amends:** Amendment A §A (ReAct thought surface) — presentation layer only; no
event, contract, or runtime change.

### D.1 Problem

Amendments A and B settled _which_ thoughts the runtime emits. They left the
presentation flat: `ThoughtTrace` rendered every `TraceEntry` — reasoning blocks
and tool executions alike — as one list of look-alike rows. Three defects
followed, all reported from a live tabular-agent turn:

1. **The reasoning block looked like a tool stuck in "running".** The
   model-native block is opened on the first reasoning token and closed only
   when the first answer delta arrives (`react_runtime.py`, §7.3 passthrough).
   The frontend assigns a row's rank at `thought_start`, so the block holds the
   lowest rank for the whole turn: permanently row #1 of the tool pile, pulsing
   `streaming_delta` under a pile of tools that start and finish beneath it.
2. **Repeated calls to one tool were indistinguishable.** Two `read_query`
   calls rendered as two byte-identical "READING QUERY" rows, because the
   redaction rule from #1774/CHAT-13 (no raw tool name, no arguments in the
   user-facing trace) leaves only the humanized label.
3. **The summary line contradicted the rows below it.** `thoughtSummaryLabel()`
   summed _tool_ latencies only and printed "Thought for 856ms" directly above a
   reasoning row reading 16.4s. And the block never collapsed: `expanded` was
   initialised `true` and the `done` prop only drove an animation, despite a
   comment claiming auto-collapse.

### D.2 Decision

Render the trace as **two lanes**, not one list:

| Lane      | Contents                               | Presentation                                                                         |
| --------- | -------------------------------------- | ------------------------------------------------------------------------------------ |
| Reasoning | `thought`, `plan`, `observation`       | `ReasoningBlock`: marker, phase label, duration, 2-line clamped preview               |
| Steps     | tool call/result combos, notes, errors | `TraceEntryRow` list: 1-based step number, status dot, label, discriminator, latency |

`splitTraceEntries()` (`traceUtils.ts`) is the single classifier. Only tool
executions are numbered; notes and errors are sequenced with them but unnumbered.

**Discriminator (defect 2).** `toolDiscriminator()` derives _volume metadata
only_ — `12 rows` / `5 sources` — from the two already-recognised curated
content shapes (`SqlQueryResult`, `RagSearchResult`, see Amendment B). The
redaction rule stands: raw arguments and raw result content are still never
rendered in the trace. A failed or unrecognised result yields no discriminator;
the red status dot already carries the failure.

**Summary (defect 3).** `traceSummary()` replaces `thoughtSummaryLabel()` and
returns structured data (`reasoningMs`, `toolCount`, `toolMs`, `running`) that
the component formats through i18n. `reasoningMs` is the **max** of the
reasoning blocks' durations, not their sum: the model-native block brackets the
tool calls and any nested reasoning, so summing would count the same wall-clock
twice.

**Collapse (defect 3).** Open while the turn streams, auto-collapsed once it is
done; an explicit toggle is persisted in `localStorage` and read once at mount,
so hiding the trace is a durable one-click action without a toggle on one turn
retroactively flipping every other trace on screen
(`resolveTraceExpanded()` is the pure, unit-tested precedence rule).

### D.3 Explicitly not changed

The lifecycle that makes the reasoning duration cover the whole turn — the
model-native block closing only at the first answer delta — is **unchanged**.
Closing it before the first `tool_call` and opening a fresh block afterwards
would make `duration_ms` mean "time actually spent reasoning", and would let the
two lanes interleave chronologically. That touches the runtime execution
contract and its event ordering guarantee (§9.5), so it is deliberately left to
a separate proposal. The presentation change above stands on its own: the
reasoning block no longer occupies a slot in the tool list, so its long-running
nature is no longer read as a stuck tool.

### D.4 Impact

Frontend only: `traceUtils.ts`, `ThoughtTrace`, new `ReasoningBlock`,
`TraceEntryRow`, new `useTraceExpansion` hook, and the first i18n coverage of
the trace surface (`rework.chatTrace.*`, en + fr — the trace was hardcoded
English). No SSE event, no persisted shape, no OpenAPI change.

---

## Amendment E — Reasoning is persisted for display; continuity measured again (2026-07-31)

**Author:** Timothé Le Chatelier
**Status:** Half implemented, half measured. §E.1 ships; §E.2 records a spike and
takes no design decision.
**Amends:** §C.9 (the scope gap), §8 (durable trace)
**Related:** `RUNTIME-EXECUTION-CONTRACT.md` §8.31

### E.1 The display half — closed

§C.9 observed that this RFC specifies how reasoning is *surfaced* and never what
happens to it afterwards. One half of that gap had a plain user-visible cost:
**reasoning disappeared on page reload.** `_write_turn_history` never mapped the
`thought_*` kinds, so nothing was ever written on `Channel.thought` — a channel
that had existed in the stored schema all along, with a frontend already able to
render it and a read endpoint already returning it. Only the writer was absent.

That is now implemented; `RUNTIME-EXECUTION-CONTRACT.md` §8.31 is the normative
record, including the four rules that make a reloaded trace match the live one.

Note what this does **not** do: it changes nothing about what is replayed to the
model. §8's `thought_trace` on `GraphExecutionOutput` (evaluation/replay) and this
history row (display) remain separate surfaces, deliberately.

### E.2 The continuity half — a spike, and one closed door

Amendment C §C.10 q2 proposed a one-hour spike on `use_previous_response_id`,
noting that settling it first *"may remove the need for a multi-day client
migration"*. It was run on 2026-07-31. **It does not: the door is closed.**

| Probe | Result |
| ----- | ------ |
| `POST https://api.mistral.ai/v1/responses` | **HTTP 404, "no Route matched with those values"** — Mistral exposes no Responses API at all |
| `_format_message_content`, langchain-openai **1.3.2** | still drops `thinking` / `reasoning_content` on `chat/completions` **and** `responses` — §C.4 re-confirmed at the current version |
| Same reasoning text carried by a `{"type": "text"}` block | **survives the filter intact** |
| Verbatim replay still accepted by the API (§C.5's absent 422) | **HTTP 200** — §C.5 confirmed, the documented 422 remains unreproducible |

> _Harness note, recorded because it nearly produced a wrong conclusion:_ the
> first replay attempt returned HTTP 400
> `invalid_request_message_order` (code 3230) and was briefly read as "the API
> refuses the reasoning". It does not — the model had emitted **two** tool calls
> and the harness supplied one tool response. One response per call, and the
> same replay returns 200. Mistral rejects the message *count*, not the
> `thinking` block.

**The framing that makes this legible** (developer's, 2026-07-31): continuity is
a property of the *endpoint*, not of the vendor. A **stateful** API keeps the
reasoning items server-side and hands back a reference (`previous_response_id`);
nothing needs replaying. A **stateless** API keeps nothing, so the client must
resend the reasoning itself. Anthropic is proprietary and stateless — it
*requires* verbatim replay of signed `thinking` blocks inside a tool-use turn,
exactly like an open-weight endpoint. So the axis is stateful/stateless, not
proprietary/open.

Consequence for Fred, whose whole catalogue routes through the OpenAI-compatible
client: Mistral is stateless **and** has no Responses endpoint, so the provider
cannot be asked to hold the reasoning. Client-side replay is the only branch left.

**The opening.** The filter keys on the block's `type` discriminator and nothing
else. Re-homing the reasoning into an ordinary `text` block traverses it
untouched, with no client fork, no patched `_format_message_content`, and no
dependency pin.

### E.3 Measured — re-homed reasoning suppresses the drift completely

Implemented as `thread_reasoning_within_open_turn` (`support/thinking.py`) and
measured on 2026-07-31, same day, on the **real Fred stack** (`ChatOpenAI` +
`bind_tools` + the real functions), 12 trials per condition, `mistral-small-latest`,
temperature 0, one tool, a constant tool result, §C.11's duplicate definition.

| Prompt | Condition | Turns with a duplicate | Duplicates | Tool calls / trial |
| ------ | --------- | ---------------------- | ---------- | ------------------ |
| Fred's real prompt | `strip_reasoning_from_history` (today) | 2 / 12 | 6 | 2.50 |
| Fred's real prompt | `thread_reasoning_within_open_turn` | **0 / 12** | **0** | 2.08 |
| Fred's real prompt | reasoning disabled | 0 / 12 | 0 | 2.00 |
| Bare prompt | `strip_reasoning_from_history` (today) | 9 / 12 | **67** | **7.50** |
| Bare prompt | `thread_reasoning_within_open_turn` | **0 / 12** | **0** | 2.00 |
| Bare prompt | reasoning disabled | 0 / 12 | 0 | 1.83 |

One-sided Fisher exact, bare prompt (9/12 vs 0/12): **p = 1.7 × 10⁻⁴**. On the
real prompt (2/12 vs 0/12) the difference is directionally identical but **not
significant at n = 12 (p = 0.24)** — stated plainly rather than rounded into a
claim the sample does not support.

**Three readings, in order of what they settle:**

1. **The concern in the previous draft was wrong, and strongly so.** Text-re-encoded
   replay does not merely match verbatim replay, it beats it: §C.6's verbatim
   replay went 6/12 → 1/12 (p = 0.034), this goes 9/12 → 0/12. The worry that a
   `text` block would carry less weight than a privileged `thinking` block is not
   what the data shows.
2. **It does not win by breaking the loop.** The candidate makes 2.00–2.08 tool
   calls per trial — the same as the reasoning-disabled control (1.83–2.00) and
   the count the question actually warrants. Today's behaviour inflates that to
   **7.50 on a bare prompt: 90 calls where 24 suffice**. Checking this was not
   optional; a "fix" that suppressed duplicates by suppressing tool use would
   have produced identical duplicate counts and been worthless.
3. **§C.7's masking is re-confirmed, and it is the real argument for shipping.**
   The same code drifts 9/12 with a bare prompt and 2/12 with Fred's. The
   protection in production still rests on prompt wording — the "load-bearing
   dependency that nobody has written down". This change makes it structural: the
   candidate holds at 0/12 in **both** prompt regimes, so a future rewording of
   `TOOL_REPETITION_RULE` can no longer silently re-expose the defect.

### E.4 What the model actually receives — and the echo risk, measured

Asked before the switch was flipped, and worth recording because the answer is
uncomfortable and load-bearing: **the reasoning is injected as ordinary assistant
speech, and there is no protocol-level way to mark it as anything else.** The
exact payload:

```json
{
  "role": "assistant",
  "content": "[your reasoning so far this turn] Je n'ai pas le contrat en contexte…",
  "tool_calls": [{ "type": "function", "id": "c1", "function": { … } }]
}
```

That `content` field is the same one the model writes a user-facing reply into.
`RECALLED_REASONING_PREFIX` is a **textual convention, not a guarantee** — on an
OpenAI-compatible endpoint the only channel carrying privileged "this is
reasoning" semantics is the `thinking` block, which the client drops (§E.2).
Anyone reading this later should not imagine a stronger separation than exists.

**The consequent risk — the model repeating its reasoning to the user — was
measured: 0 / 8 final answers contaminated.** Every answer opened on the contract
content ("D'après les documents contractuels : …"), none narrated the act of
searching, none reproduced the marker. Small sample, one scenario; enough to say
the risk does not materialise here, not enough to call it impossible.

**Status: implemented, tested, and wired** (2026-07-31).
`CheckpointHygieneMiddleware` calls `thread_reasoning_within_open_turn`. Two
tests in `test_react_middleware_frame.py` pin both halves — open-turn reasoning
reaches the model as text, closed-turn reasoning is still dropped — because the
wiring is one line whose absence is invisible: the loop keeps working, it just
silently repeats tool calls again.

**Limits of this evidence, stated so the next reader does not overclaim.** One
model, one question, one tool, one API generation, 12 trials (8 for the echo
test). The production-prompt result is under-powered. Nothing here measures
answer quality, latency, or token cost — only duplicate tool calls. Re-homed
reasoning is ordinary content, so it does consume context tokens that the
previous emptied-content behaviour did not.

§C.9's two coherent resolutions are now decidable: option 2 — a "Layer 2c —
reasoning continuity" section stating the thread-within-open-turn rule as part of
this contract — is the one the evidence supports.
