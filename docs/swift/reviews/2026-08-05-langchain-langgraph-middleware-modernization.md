# LangChain/LangGraph middleware modernization audit

**Date:** 2026-08-05

**Scope:** `libs/fred-runtime`

**Status:** architectural assessment and deletion-first roadmap; no implementation

**Tracking:** [GitHub epic #2227](https://github.com/ThalesGroup/fred/issues/2227)

## Executive conclusion

Swift already runs its ReAct execution path through LangChain `create_agent()`
and a platform middleware frame. The next step is not another loop rewrite. It
is to finish the convergence by delegating generic lifecycle mechanics to
LangChain/LangGraph while keeping FRED policy and public contracts in FRED.

The target separation is:

- `fred-core`: security, ReBAC/C3, audit and domain policy — **what** must be
  enforced;
- `fred-sdk`: capability, HITL and runtime-event contracts — **what** authors
  and clients can rely on;
- `fred-runtime`: thin FRED policy adapters plus LangChain/LangGraph lifecycle
  hooks — **where** model/tool behavior is enforced;
- FRED checkpointer, admission and stream adapters: persistence, distributed
  resume safety and the frozen SSE contract.

`fred-core` is outside the refactoring scope. No big-bang rewrite is proposed.

## Current state

The ReAct runtime builds a stock `create_agent()` graph with this platform
frame:

1. `CheckpointHygieneMiddleware`
2. `ModelRoutingMiddleware`
3. `DynamicPromptMiddleware`
4. capability middleware block
5. `TracingKpiMiddleware`
6. `ToolObservabilityMiddleware`
7. `FredHitlMiddleware`
8. native `ToolCallLimitMiddleware`, when configured

The custom hook inventory is small and explicit:

| Component | Hook | Assessment |
| --- | --- | --- |
| `CheckpointHygieneMiddleware` | `awrap_model_call` | Keep tool-call pairing and reasoning hygiene; evaluate native context editing only for generic trimming. |
| `ModelRoutingMiddleware` | `awrap_model_call` | Keep custom: FRED owns model/operation policy. |
| `DynamicPromptMiddleware` | `awrap_model_call` | Keep thin; consolidate prompt fragments and preserve structured content blocks. |
| capability MCP instructions | `awrap_model_call` | Fold into deterministic dynamic prompt composition. |
| `TracingKpiMiddleware` | `awrap_model_call` | Keep custom: FRED owns KPI vocabulary, privacy and correlation. |
| `ToolObservabilityMiddleware` | `awrap_tool_call` | Split authorization from observability. |
| `FredHitlMiddleware` | `aafter_model` | Main candidate for native HITL plus a FRED contract adapter. |
| `ToolCallLimitMiddleware` | native `after_model` | Already correctly delegated. |
| `ContextAwareTool` | MCP tool wrapper | Keep context injection; delegate exception-to-`ToolMessage` conversion. |
| `ExpiredTokenRetryInterceptor` | MCP transport interceptor | Keep transport-specific; make refresh async rather than treating it as a generic tool retry. |
| ReAct stream executor | LangGraph stream adapter | Keep the contract adapter, remove control-flow policy from it over time. |

There are no custom `before_agent` or `after_agent` hooks today. Adding them is
not an objective by itself.

## Principal findings

### 1. The platform frame does not fully guarantee governance ordering

LangChain tool wrappers are composed with the first wrapper outermost, while
`after_model` hooks run in reverse middleware order. The current capability
slot therefore leaves two latent bypasses:

- a capability `wrap_tool_call` can short-circuit before platform
  authorization/observability;
- a capability `after_model` runs after the current HITL gate and can mutate or
  add tool calls after approval evaluation.

No current capability was found exploiting this, but the platform invariant is
not structurally guaranteed.

The semantic target is:

```text
tool call:   authorization -> observability -> error handling -> capability -> tool
after_model: capability -> call limit -> filesystem rewrite -> HITL
```

The frame should be ordered and tested per hook semantics rather than presented
as one conceptual capability insertion block.

### 2. Authorization and observability are combined incorrectly

`ToolObservabilityMiddleware` emits `agent.tool.invocation.started` before the
per-tool ReBAC check. This contradicts the audit contract: a proposal refused
before execution is not an action and must not produce a tool audit event.

Split it into:

- `FredToolAuthorizationMiddleware`: fail-closed ReBAC enforcement;
- `ToolObservabilityMiddleware`: KPI/audit only, reached after authorization.

The ReBAC decision remains FRED policy. `awrap_tool_call` is only its execution
mechanism.

### 3. Tool failures have competing representations

`document_summarize` reports failures through
`ToolInvocationResult(is_error=True)`, while tool observability recognizes only
`ToolMessage.status == "error"`. The stream adapter later detects the artifact
and suppresses the next model answer.

This can make one failure user-visible but KPI/audit-visible as success, and it
puts loop-control policy in the transport adapter.

Normalize failures into a `ToolMessage(status="error")`, preferably through
native `ToolErrorMiddleware`, while retaining the typed FRED artifact required
by Graph and frontend consumers.

### 4. Native HITL is useful but is not a drop-in replacement

LangChain `HumanInTheLoopMiddleware` already provides conditional tool gates,
batched interrupts, decisions and resume handling. FRED nevertheless has
additional frozen behavior:

- localized `HumanInputRequest` wire payload;
- `proceed`/`cancel`, not native `approve`/`reject`;
- one decision applies atomically to the whole batch;
- cancel skips gated and ungated calls from the model turn;
- targeted `interrupt_id` resume and distributed single-use admission.

The safe migration is a compatibility spike:

1. map `HitlSpec` to native interrupt configuration;
2. translate native HITL requests to `HumanInputRequest`;
3. expand the one FRED decision into the native per-action decisions;
4. prove the existing batch and replanning behavior;
5. retain a small FRED gate if native behavior cannot be adapted without
   copying private LangChain implementation.

### 5. Native HITL cannot replace FRED's distributed claim

LangGraph owns checkpointed interrupt/resume semantics. FRED's SQL claim owns a
different boundary: atomic admission of concurrent HTTP resumes across runtime
replicas. Native HITL does not supply that property.

`FredSqlCheckpointer`, exact interrupt validation and the durable resume claim
remain custom unless a future library capability proves the same distributed
guarantee.

### 6. ReAct, Deep and Graph have different convergence paths

- ReAct is already on `create_agent()` and is the primary middleware target.
- Deep uses middleware but rejects tool approval and per-turn tool-call limits;
  it should consume shared frame primitives after hook-order compatibility is
  verified.
- Graph is a deterministic SDK runtime. It must not be forced into
  `AgentMiddleware`; shared authorization/observability should be exposed at a
  runtime-independent FRED execution envelope or through agentic subgraphs.

### 7. Adjacent runtime debt must stay separate

Synchronous Keycloak refresh inside async MCP/KF paths is a real event-loop
blocking bug, but it belongs to the transport/authentication layer. Native
`ToolRetryMiddleware` must not duplicate it. Generic tool retry should be
opt-in and limited to idempotent tools.

Other explicit policy gaps are the decorative `allow_parallel_calls`, absence
of a model-call limit, and absence of an approved model retry/fallback policy.

## Boundary definition

### Must remain FRED-owned

- ReBAC/C3 rules, permission vocabulary and fail-closed decisions;
- audit event vocabulary, bounded dimensions and privacy constraints;
- `HitlSpec`, `HumanInputRequest`, `RuntimeEvent`, `ToolInvocationResult`;
- capability resolution, typed runtime services and context;
- model routing and permitted fallback policy;
- SQL checkpointer, session validation and distributed resume claims;
- LangGraph stream to FRED SSE translation;
- MCP context injection and authentication refresh.

### Can be delegated to LangChain/LangGraph

- generic model/tool loop lifecycle;
- model/tool call wrapping;
- graph interrupts and resume mechanics;
- tool/model call limits;
- selected exception-to-message conversion;
- retry/fallback after FRED defines eligibility and budgets;
- generic context pruning or summarization.

## Deletion-first roadmap

### Phase 0 — scope and contract oracle

- Close completed historical implementation issues and use one modernization
  epic for the remaining work.
- Freeze the current HITL wire, batch, interrupt identity, authorization/audit,
  error, prompt and stream invariants.
- Run the native HITL compatibility spike against the locked LangChain and
  LangGraph versions.
- Specify and test the target order of every hook type.
- Decide model-call limits, retry eligibility and fallback policy before
  enabling any built-in retry middleware.

Exit condition: no unresolved semantic difference is hidden inside a proposed
middleware replacement.

### Phase 1 — focused platform middleware

- Extract filesystem argument rewriting from HITL.
- Split tool authorization from tool observability and correct audit ordering.
- Put platform tool guards outside capability wrappers.
- Introduce native `ToolErrorMiddleware` with a bounded FRED error formatter.
- Remove catch-as-success paths from `ContextAwareTool` and capability tools.
- Replace or reduce `FredHitlMiddleware` only after the compatibility spike.
- Keep MCP authentication retry outside generic tool retry.

Deletion target: materially reduce the current 483-line HITL implementation and
remove duplicated error/control paths. No new abstraction should survive unless
it replaces at least two existing owners.

### Phase 2 — loop and runtime simplification

- Share frame primitives between ReAct and Deep.
- Add Deep parity for supported capabilities, HITL and call limits.
- Remove artifact-error loop control from the SSE transcoder.
- Evaluate native context editing/summarization for generic trimming while
  retaining FRED tool-pairing and poisoning defenses.
- Persist `exchange_id` in durable run/checkpoint state instead of recovering it
  from fire-and-forget history.
- Add model-call limits and opt-in retry/fallback only after Phase 0 policy
  decisions.

Indicative cumulative deletion budget: 350–600 production lines, to be measured
from the actual diff rather than treated as an acceptance criterion by itself.

### Phase 3 — validation

- Hook-order and short-circuit contract tests.
- HITL proceed/cancel, mixed batch and sequential-interrupt tests.
- PostgreSQL and multi-runtime concurrent resume tests.
- ReBAC denial with zero tool audit events.
- Consistent `DocumentSummarize` artifact, `ToolMessage`, KPI and SSE failure.
- ReAct/Deep parity and idempotent-tool-only retry coverage.
- Performance comparison of the model/tool hot path.
- Contract documentation and generated clients only if a public wire changes.
- Production-line deletion measurement and same-change removal of superseded
  paths.

## Recommended execution packages

1. **Frame governance:** hook ordering, authorization/observability split and
   audit correctness.
2. **Native HITL compatibility:** contract adapter, batch semantics, targeted
   resume and preservation of distributed claims.
3. **Tool failure normalization:** native error middleware, capability/MCP
   errors and SSE simplification.
4. **Runtime convergence:** Deep parity, context windowing and explicit
   call/retry/fallback policies.

## Scope exclusions

- no changes to `fred-core` contracts;
- no wholesale GraphRuntime rewrite;
- no deletion of SQL resume claims based only on native HITL adoption;
- no blanket retry for side-effecting tools;
- no SSE/public HITL contract change without a separate explicit decision.

## Issue consolidation performed on 2026-08-05

Closed as delivered:

- #1971–#1982 — the CAPAB-01 capability and `create_agent()` foundation;
- #1988 — MCP capability id, team scope and normal ReBAC path;
- #2011 — platform-wide MCP/capability tool observability coverage;
- #2177 — default HITL safeguard for `summarize_document`;
- #2179 — ReAct V2 targeted HITL resume and checkpoint convention fix.

Closed as superseded by epic #2227:

- #1432 — model-input history windowing;
- #2074 — structural tool-failure visibility;
- #2216 — only the remaining `exchange_id` race was carried forward; the
  stale-interrupt and duplicate-resume protections are already delivered and
  remain required.

Deliberately kept separate and open:

- #1948 / #2125 — MCP/Keycloak authentication transport and async refresh;
- #2088 — frontend rendering of intermediate ReAct text;
- #2158 — physical persisted-checkpoint compaction.
