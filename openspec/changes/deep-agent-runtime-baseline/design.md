## Context

`DeepAgentRuntime` delegates planning to `deepagents.create_deep_agent` while keeping Fred's ReAct
transport, events, observability and SQL checkpointer. Two library facts shape this design:

- `create_deep_agent` unconditionally adds its own `TodoListMiddleware` and `FilesystemMiddleware`
  (tool names `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep`/`execute`) to every agent it
  compiles, regardless of what tools Fred passes in.
- Fred passes no explicit `backend=`, so that built-in filesystem middleware defaults to
  `deepagents`'s `StateBackend`, which stores file content as part of the LangGraph agent state and
  is checkpointed by Fred's existing SQL checkpointer after every step. Content therefore survives
  across turns of the same conversation thread (and is erased when that conversation's checkpoint
  is erased) but is not a separate, addressable object store and is not visible outside the thread.
  This design calls it Deep's **conversation-scoped checkpoint filesystem** — not a durable,
  user-visible Workspace, and not purely ephemeral either.

See `proposal.md` for why the dispatch and HITL defects mattered.

## Goals / Non-Goals

**Goals:**

- Make `DeepAgentRuntime` a real, dispatched, capability-aware, observable runtime that a developer
  can compare against `ReActRuntime` on identical inputs.
- Bring Deep to positive HITL parity with ReAct: both capability-declared and operator-configured
  approval route through the one existing `FredHitlMiddleware` gate and the one
  `HumanInputRequest`/`AwaitingHumanRuntimeEvent` transport contract, on both runtimes.
- Prove that parity at two levels — a real compiled graph, and Fred's own transport layer on top of
  it — since a graph-level pause is not yet proof that it reaches the product's event/resume
  contract.
- Record what the one manually witnessed acceptance run does and does not prove, so it is not later
  mistaken for filesystem, Workspace, or multi-step planning evidence.

**Non-Goals:**

- Any durable, user-visible file storage for Deep. No `backend=`/`CompositeBackend` is passed to
  `create_deep_agent` in this change; each built-in filesystem name remains guarded unless that
  exact name is contributed by the selected tool surface.
- A new approval mechanism. Operator-policy support on Deep is delivered by removing a rejection and
  reusing `FredHitlMiddleware`'s existing `approval_policy` handling — the same code path Deep
  already threads `approval_policy` through for capability bindings.

## Decisions

### D1 — Reuse `FredHitlMiddleware` unmodified; native `interrupt_on` was rejected

`deepagents.create_deep_agent(interrupt_on=...)` wires LangChain's own `HumanInTheLoopMiddleware`,
whose resume payload shape (`{"decisions": [{"type": "approve"|"edit"|"reject"|"respond", ...}]}`)
is structurally incompatible with Fred's frozen `HumanInputRequest` proceed/cancel contract;
`react_stream_adapter.py`'s `extract_interrupt_request` hard-raises on any interrupt payload that
doesn't validate against it, so `interrupt_on` would fail mid-turn on resume rather than at build
time. This was investigated and rejected (posted to #2227). `FredHitlMiddleware` is instead composed
into Deep's middleware list unmodified — same construction shape, same relative order (`capability
middleware → TracingKpiMiddleware → ToolObservabilityMiddleware → FredHitlMiddleware →
filesystem-tool guards`) as `build_react_platform_middleware_frame` uses for ReAct.

### D2 — Positive parity: one gate, one contract, two sources of approval, two runtimes

`FredHitlMiddleware` already accepts both `capability_hitl` bindings and an `approval_policy`
(`ToolApprovalPolicy.enabled`/`always_require_tools`) and already resolves both through the same
`_gate_decision`/`aafter_model` path for ReAct. Deep's `_build_deepagent_runtime_middleware` already
threads `approval_policy=policy.tool_approval` into its own `FredHitlMiddleware` instance; the only
remaining asymmetry was `build_executor`'s own early `NotImplementedError` when
`policy.tool_approval.enabled` was `True`, guarding a code path that was otherwise already wired
correctly. Removing that guard is a deletion, not new gating logic.

| Concern | ReAct | Deep (this change) | GraphRuntime |
|---|---|---|---|
| Capability `HitlSpec` (no-op / pause+proceed / pause+cancel) | Existing, unchanged | Same gate, same outcomes — proven at both the compiled-graph and Fred-transport levels | Not applicable — own separate HITL lifecycle (`request_human_input`, `_pending_checkpoints`), not touched by this change |
| Operator `ToolApprovalPolicy` (no-op / pause+proceed / pause+cancel) | Existing, unchanged | Same gate, same outcomes — proven at both the compiled-graph and Fred-transport levels | Not applicable |
| Resume contract | `AwaitingHumanRuntimeEvent` carrying `HumanInputRequest`, proceed/cancel | Same contract, same event/request types, same `_TransportBackedReActExecutor` code path | Not applicable |
| Filesystem tools | N/A (no Deep-style built-in filesystem) | Each `deepagents` built-in filesystem name stays guarded off (disabled prompt + `ToolCallLimitMiddleware` block) unless that exact name is bound; a partial filesystem surface never enables the remaining built-ins | N/A |

### D3 — Filesystem-tool-name overlap is enforced per tool

`deepagents`'s built-in `read_file`/`write_file`/etc. share names with what a real Fred filesystem
surface exposes. Availability is therefore derived from the exact model-visible names contributed
by resolved tools and capability tools. The disabled prompt and `ToolCallLimitMiddleware` guards
cover only the missing names: binding `ls` or `read_file`, for example, cannot expose Deep's
internally registered `execute`. `FredHitlMiddleware.rewrite_filesystem_tool_arguments` composing
correctly with a gated tool of the same name remains covered by
`test_deep_hitl_filesystem_tool_name_overlap_does_not_collide`.

### D4 — The manual NOVA-DOC run is document-access evidence, not filesystem or Workspace evidence

One witnessed run of the public NOVA-DOC factual question (`fred-corpus`'s
`public-tender-response` knowledge base: *"Quel est le prix plafond ... pour le périmètre ferme de
36 mois ... NOVA-DOC 2027 ..."*) was executed against both `fred.github.deep_assistant` (Deep) and
`fred.github.assistant` (ReAct), same neutral system prompt, same knowledge base, same question.
Both produced the identical correct grounded answer (EUR 1,800,000 excluding tax; 12 February 2027,
12:00 UTC), verified by reading `session_history` in Postgres directly rather than trusting the chat
UI (RUNTIME-EXECUTION-CONTRACT.md's own documented display-layer caveat, #2588). Deep used
approximately 14k input tokens against ReAct's approximately 10k for the same output, on this one
run.

Both runs invoked only `search_documents_using_vectorization` — no filesystem tool call, no
Workspace object, no S3/SeaweedFS write occurred in either run. This evidence proves Deep's
capability/tool-binding and observability wiring reach parity with ReAct on a simple grounded
document-access question; it proves nothing about filesystem behavior, multi-step planning, or the
tender scenario's own rubric, and must not be read as such.

### D5 — OpenSpec is the durable behavioral source; the runtime contract stays compact

Once this change is archived, `deep-agent-runtime` and `agent-human-approval` become part of the
main `openspec/specs/` tree and are the durable record of Deep's dispatch, capability wiring,
observability and HITL parity behavior. `RUNTIME-EXECUTION-CONTRACT.md` keeps only compact
architecture and invariant statements for these areas plus a link to the two OpenSpec capabilities
— it stops being where the behavioral chronology accretes. `tasks.md`'s closing group carries the
sync/archive step that moves these deltas into `openspec/specs/`.

### D6 — Per-turn graph compilation is a separate runtime-lifecycle investigation

Fred currently creates a fresh runtime for every turn, so both runtimes synchronously rebuild their
compiled LangGraph executor on the event loop. A local 20-iteration micro-benchmark measured a
median of 3.1 ms for ReAct construction and 15.3 ms for Deep construction. The larger Deep cost is
primarily the `deepagents` assembly of its main graph, built-in middleware and default general-purpose
subagent; the repeated payment on every turn comes from Fred's runtime lifecycle. This behavior
predates the HITL changes but becomes production-reachable through the dispatch correction.

This change neither selects nor implements an optimization. In particular, a compiled Deep graph
contains tools and middleware built from `BoundRuntimeContext`; caching it only by agent definition,
toolset or capability identity is not proven safe across teams, users or sessions. Load measurement,
immutable-versus-bound graph separation, cache invalidation and multi-pod behavior belong to a
separate investigation starting from `swift`.

## Risks / Trade-offs

- **Removing Deep's operator-policy rejection changes observed behavior for any operator who already
  has `always_require_tools` configured on a Deep template.** Before this change, enabling that
  policy on a Deep agent made every turn fail at build time; after this change, it gates the named
  tools instead, same as ReAct. This is the intended fix, not an incidental side effect, but it is a
  real behavior change for any such template and is called out here rather than folded silently into
  the capability-HITL work.
- **A compiled-graph proof and a Fred-transport proof are not redundant.** The transport layer
  converts a raw LangGraph interrupt into `AwaitingHumanRuntimeEvent`/`HumanInputRequest` and
  resumes through `graph_input_from_react_input`'s targeted `Command(resume={interrupt_id:
  payload})` form — a different code path than a bare `Command(resume=payload)` against the compiled
  graph directly. Both levels are tested so a defect in either layer is caught.
- **`basedpyright` and comment-density cleanup are tracked, not silently absorbed.**
  `test_deep_agent_dispatch.py` has 2 `reportIncompatibleVariableOverride` errors (its two fake
  runtime classes each override `instances: list[_RecordingRuntime]` with an invariant, narrower
  list type) and 1 `reportUnreachable` warning, confirmed by running `basedpyright` directly. Fixed
  in this change (`tasks.md` §4).
