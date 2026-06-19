# RFC: Typed, Scoped Agent Invocation (agents-as-tools)

**Status:** Phase 1 implemented (2026-06-18) — see §11
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**ID:** AGENT-INVOKE
**Scope:** swift `libs/fred-sdk` (contracts) + `libs/fred-runtime` (the agent invoker)
**Contract impact:** **additive** — `invoke_agent` gains two optional parameters and
the result gains one optional field; today's calls keep working unchanged
**Driver:** the rags assessment agent (Eva, CMDB enrichment) and Chronos (M2C retex);
generalises to any agent-to-agent composition

---

## 1. Decision (in one paragraph)

Let one agent invoke another **like a typed function call**, not just a chat turn.
Extend `GraphNodeContext.invoke_agent(...)` so the caller can **(a)** declare the
**output schema** it expects and receive a **validated typed object**, and **(b)**
pass a **per-call scope** (which documents/libraries the callee may search, search
policy) that narrows the callee's world for that one invocation. This is **additive**
and, crucially, **reuses machinery the platform already has** — structured-output
forcing and the `RuntimeContext` retrieval-scope fields — rather than introducing a
new subsystem.

---

## 2. Problem (functional)

An agent calling another agent can be modelled two ways:

- **As a conversation** — *send a message string, get a message string back.* This is
  what `invoke_agent(agent_id, message) -> AgentInvocationResult` (`.content: str`)
  does today.
- **As a function call** — *pass typed input + an execution scope, get a typed result
  back.*

Real composition needs the function-call shape:

- **Eva — CMDB enrichment.** For each documented technology, Eva asks Tessa (tabular)
  *"is `X` installed on these CSVs, and which version?"* and needs a **structured**
  `{component, version}` answer, scoped to **those specific CSV documents**. With the
  conversational contract she gets free text to **regex-parse** (fragile) and **cannot
  tell Tessa which documents to look at**.
- **Chronos — M2C retex.** Wants Rico's corrective-RAG answer **scoped to the retex
  library**. Same two gaps.

Both hit the same root cause, in two dimensions:

| Dimension | Needed | `invoke_agent` today |
| --- | --- | --- |
| **Typed output** | a validated object (schema-checked) | `content: str` → parse it yourself |
| **Per-call scope** | "answer, but only over *these* documents" | inherits the ambient request scope only |

The legacy v1 agents had both (they passed `output_structure` and
`selected_document_uids` straight into the sub-agent's graph). The published contract
narrowed that to a chat message, so the capability was lost.

---

## 3. Why this is a small change, not a new subsystem

Both halves already exist in the platform — they are just not wired to `invoke_agent`:

- **Typed output** — the graph runtime already forces structured output for models
  (`resolved_model.with_structured_output(...)`), and the Workflow tooling already
  appends a *StructuredOutput* instruction to a sub-agent and validates the result.
  We apply the same mechanism to a sub-agent's **final** output.
- **Per-call scope** — `RuntimeContext` already carries
  `selected_document_libraries_ids`, `selected_document_uids`, `search_policy`,
  `search_rag_scope`. The callee's tools already honour these. The only gap is letting
  the **caller of `invoke_agent`** set them for that one invocation.

So this RFC is mostly **plumbing**: route a caller-supplied scope into the callee's
`RuntimeContext`, and route a caller-supplied schema into the callee's output
validation. That is why it is "not too complex."

---

## 4. The capability (contract)

Extend the author-facing call and the result; everything new is **optional**.

```
async def invoke_agent(
    agent_id: str,
    message: str,
    *,
    prior_turns: tuple[ConversationTurn, ...] = (),
    output_schema: type[BaseModel] | None = None,   # NEW
    scope: InvocationScope | None = None,            # NEW
) -> AgentInvocationResult
```

**`output_schema`** — when given, the runtime instructs the callee to produce that
shape and **validates** the callee's final output against it (with bounded retry, as
`structured_model_step` does today). The result carries the validated object.

**`scope: InvocationScope`** — a small, explicit narrowing of the callee's world for
this call, drawn from the fields `RuntimeContext` already has:

```
class InvocationScope(BaseModel):
    document_uids: list[str] | None = None
    library_ids: list[str] | None = None
    search_policy: Literal["strict", "hybrid", "semantic"] | None = None
```

The runtime derives the callee's `RuntimeContext` from the caller's, **overriding only
these fields** (auth/session inherited — see §5).

**Result** — `AgentInvocationResult` gains one optional field:

```
class AgentInvocationResult(FrozenModel):
    content: str                       # unchanged
    structured: BaseModel | None = None   # NEW — present iff output_schema was given
    # ui_parts, sources … unchanged
```

That is the whole surface: two optional inputs, one optional output field.

---

## 5. Auth & safety (the part to get right)

- **Scope narrows, never widens.** `InvocationScope` can only *restrict* what the
  callee sees. It cannot grant access the caller (or callee's user) doesn't already
  have — ReBAC/document permissions are still enforced by the callee's tools against
  the **delegated identity**.
- **Identity is inherited, not forged.** The callee runs as the caller's delegated
  auth/session; `scope` selects *among* what that identity may read.
- **Output validation is bounded.** Schema mismatch retries a fixed number of times,
  then fails the call cleanly (the caller decides how to degrade) — no infinite loop.
- **Composition depth is bounded.** A simple max invocation depth / cycle guard
  prevents runaway agent-calls-agent chains.

---

## 6. What it unlocks (consumers)

- **Eva — CMDB.** `await invoke_agent("rags.tabular.tessa.react", question,
  output_schema=CmdbComponentExtraction, scope=InvocationScope(document_uids=csv_uids))`
  → a validated `{component, version}` over exactly the CSV documents. The deferred
  CMDB group becomes implementable; no text parsing.
- **Chronos — M2C retex.** Invoke Rico with `scope=InvocationScope(library_ids=[retex])`
  instead of the current resolve-then-search workaround.
- **Everyone else.** Any "agent A delegates a bounded, typed sub-task to agent B"
  pattern (review panels, extractors, verifiers) becomes robust.

---

## 7. Phasing

- **Phase 1 (this RFC):** `output_schema` + `scope` on `invoke_agent`; `structured` on
  the result. Solves Eva-CMDB and Chronos-retex. Small, additive.
- **Phase 2 (future, optional):** agents **declare typed skills** — named operations
  with input/output schemas — and `invoke_agent(agent_id, skill, typed_input, scope)`.
  This is the full "agent as a typed service" model; defer until a second concrete
  need appears, to avoid over-design.

> Design note: where a sub-task is *deterministic* (not genuinely agentic), prefer
> exposing it as a **shared capability/tool** the caller invokes directly (as was done
> for targeted similarity search) over nesting an agent. This RFC is for the cases that
> genuinely need the callee's *reasoning* (e.g. Tessa writing SQL).

---

## 8. Decisions to settle

1. **Scope fields for v1** — `document_uids` + `library_ids` + `search_policy` enough,
   or also `search_rag_scope` / `context_prompt_text`? *Recommend the three above.*
2. **Output-forcing mechanism** — reuse the Workflow/StructuredOutput "append a
   structured-output instruction + validate" path, or a dedicated final-output
   validator? *Recommend reuse.*
3. **Where the callee surfaces structured output** — its `build_output`/final node, or
   a runtime-level extraction from `content`? *Recommend the callee's typed output.*
4. **Depth/cycle limit** — what default max composition depth?

---

## 9. Acceptance criteria

- `invoke_agent(..., output_schema=S)` returns `result.structured` validated as `S`
  (bounded retry on mismatch); existing callers (no schema) are unchanged.
- `invoke_agent(..., scope=InvocationScope(document_uids=[…]))` runs the callee with
  its retrieval restricted to those documents; results never include content outside
  the scope, and never exceed the delegated identity's permissions.
- No regression to today's conversational `invoke_agent`.
- Eva's CMDB enrichment and Chronos's retex step can drop their workarounds.

---

## 10. Out of scope

- Declared typed skills / typed *input* schemas (Phase 2, §7).
- Cross-process / remote agent transport changes (this is about the contract, not the
  wire).
- Agent business logic in the rags pod (it only *consumes* this).
- Replacing the conversational `invoke_agent` — it stays for chat-shaped sub-calls.

---

## 11. Implementation (Phase 1 — landed 2026-06-18)

Shipped, additive, all existing `invoke_agent` callers unchanged.

**`libs/fred-sdk`**
- `contracts/context.py`: new `InvocationScope` (`document_uids`, `library_ids`,
  `search_policy`); `AgentInvocationRequest` gains `scope` + `output_schema` (JSON
  schema dict); `AgentInvocationResult` gains `structured: dict | None`.
- `graph/runtime.py`: `GraphNodeContext.invoke_agent` protocol gains
  `output_schema: type[BaseModel] | None` + `scope: InvocationScope | None`.
- `InvocationScope` exported from the `fred_sdk` public API.

**`libs/fred-runtime`**
- `graph/graph_runtime.py`: `invoke_agent` now appends a schema instruction when
  `output_schema` is given, parses the callee's reply (whole-string / fenced /
  embedded JSON), validates it against the schema, and attaches `result.structured`.
  Bounded retry (`_STRUCTURED_OUTPUT_MAX_ATTEMPTS = 2`); on persistent failure
  `structured=None` and a warning is logged (the call still returns the text).
- `app/agent_app.py`: `LocalRegistryAgentInvoker` applies `request.scope` onto the
  callee's context dict (`selected_document_uids`, `selected_document_libraries_ids`,
  `search_policy`), which the callee's `RuntimeContext` build reads back.
- Tests: `tests/test_graph_runtime_invoke_agent.py` (helpers + structured + retry +
  scope passthrough + backward-compat) and a scope case in `tests/test_agent_app.py`.

**Deviation from §8.3.** Phase 1 obtains structured output by **runtime-side
extraction from the callee's text** (prompt instruction + parse + schema-validate),
not by the callee declaring native typed output. This needs no change to existing
callee agents (e.g. ReAct Tessa) and is transport-agnostic. Native typed output
(`build_output`) remains the Phase 2 direction. `output_schema` is also carried on
`AgentInvocationRequest` so a future transport can force JSON natively.

**Settled decisions (§8).** (1) scope fields = `document_uids` + `library_ids` +
`search_policy`; (2) reuse parse-and-validate; (3) runtime-side extraction for Phase 1;
(4) bounded retry = 2 attempts.

**Consumers / next step.** `apps/rags-agents` (Eva CMDB, Chronos retex) can adopt this
once the new `fred-sdk`/`fred-runtime` is published; until then the rags pod keeps its
HTTP/search workarounds. No rags code ships in this change.
