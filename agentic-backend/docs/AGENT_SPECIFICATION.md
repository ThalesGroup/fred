# Fred Agent Runtime Contract v2 (Normative Specification)

Status: active target, partially implemented
Audience: Fred maintainers and agent authors
Scope: agent authoring API, runtime lifecycle, inspection, caching, execution semantics
Non-goals: detailed implementation plan, migration steps per agent (tracked separately)

This document defines the intentional, long-term contract for Fred as a runtime platform.
It replaces the ambiguous interpretation of `_graph`, reduces lifecycle surface for agent authors,
and hardens invariants to prevent semantic drift.

Current implementation status:

- `ReActAgentDefinition` is executable in production paths
- `GraphAgentDefinition` now has a first executable runtime and a first business-shaped demo
- inspection is now the canonical safe introspection surface

Remaining work is mainly:

- broader graph authoring coverage
- more UI around inspection
- continued migration away from legacy `AgentFlow`

## 1. Design Intent

Fred is a runtime platform for agents.

An agent is a declarative component that provides:

- static metadata (role, description, tags, fields)
- declared tool requirements
- an execution description (graph factory, policy, or proxy contract)

Fred runtime owns:

- dependency binding (models, MCP, stores, clients)
- lifecycle orchestration (bind, activate, dispose)
- execution (streaming, memory, checkpointing)
- inspection (safe, non-activating)
- caching and reuse semantics
- observability (metrics, tracing, logging)

Agent authors MUST NOT manage runtime activation, compilation caching, or platform I/O in structural paths.

## 2. Normative Language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, MAY are to be interpreted as in RFC 2119.

## 3. Core Entities and Separation of Concerns

Fred defines two primary concepts:

### 3.1 AgentDefinition (pure, inspectable)

AgentDefinition is the author-facing declaration of an agent.

Properties:

- stable agent identifier (string)
- metadata (role, description, tags)
- field schema (tuning fields)
- tool requirements (names/capabilities)
- execution category (see section 6)
- optional preview/inspection artifact (see section 5)

AgentDefinition MUST be buildable and inspectable without activating runtime dependencies.
AgentDefinition MUST NOT perform external I/O.

### 3.2 AgentRuntime (activated, executable)

AgentRuntime is the platform-owned runtime instance derived from an AgentDefinition and a RuntimeContext.

AgentRuntime owns:

- bound runtime context and context-scoped helpers
- activated dependencies (models, MCP sessions, remote clients)
- compiled execution artifacts (compiled graphs, tool routers, policies)
- execution entrypoints (streaming and invoke)
- disposal logic

AgentRuntime MAY be cached and reused by the platform (section 7).

Agent authors SHOULD NOT directly instantiate AgentRuntime.
Agent authors implement AgentDefinition and small execution hooks only.

## 4. Hard Invariants (Non-Negotiable)

Fred MUST enforce the following invariants by design, tests, and runtime assertions.

### Invariant A: One meaning for executable execution entrypoint

There is exactly one official executable entrypoint:

- `AgentRuntime.get_executor(...)` or equivalent platform method that returns an executable runner.

Any internal `_graph` or structural representation MUST NOT be relied upon as the executable artifact.
Agent authors MUST NOT assume that a structural graph is executable.

### Invariant B: Inspection never depends on activation

All inspection endpoints MUST succeed without:

- model binding
- MCP initialization
- remote client creation
- disk/network I/O

Inspection MUST be metadata-first (section 5).

### Invariant C: Context refresh rebinds context-scoped helpers

When a runtime context changes, the platform MUST rebind context-scoped helpers
such that reuse behavior is equivalent to fresh bind for the same context.

"set-only" refresh that skips rebind is forbidden.

### Invariant D: Compilation is deterministic and not order-dependent

Compiled execution artifacts MUST NOT have order-dependent behavior.

If an execution artifact depends on compilation parameters (e.g., checkpointer),
the platform MUST either:

- key caching by those parameters, or
- define a single canonical configuration and enforce it, or
- compile per-run without caching

The "first call wins" single-slot caching behavior is forbidden.

### Invariant E: No platform I/O in structural paths

Agent structural paths (definition construction, inspection, preview building)
MUST NOT perform external I/O:

- no network calls
- no filesystem reads (except optional embedded package resources if explicitly allowed)
- no remote auth/session creation

Any required I/O MUST happen inside platform-owned activation steps.

## 5. Inspection Contract (Single Mechanism)

Fred defines exactly one inspection mechanism:

- `inspect_agent(definition: AgentDefinition) -> AgentInspection`

The old `/agents/{id}/graph` endpoint is superseded by `/agents/{id}/inspect`.
New work MUST treat `inspect` as the only canonical introspection surface.

### 5.1 AgentInspection payload

AgentInspection is a structured payload containing:

- agent_id
- role, description, tags
- field schema (including UI hints)
- execution category
- declared tool requirements (names, optional capability descriptors)
- preview (optional):
  - `preview.kind` in {"none", "mermaid", "dag", "text"}
  - `preview.content` (string)
  - `preview.note` (optional reason or limitations)

Inspection MUST be safe and non-activating.
Inspection MUST NOT compile executable graphs.
Inspection MUST NOT call activation hooks.

### 5.2 Preview rules

An agent MAY provide a preview artifact.
Preview is best-effort and MUST NOT be required for correctness.

If a preview cannot be provided safely, the agent MUST return `preview.kind="none"` with a `note`.

Preview MUST be treated as informational only.
Preview MUST NOT be used to derive or infer executable behavior.

## 6. Execution Categories (Strict, Limited Set)

To prevent semantic drift, Fred supports a small number of execution categories.
Each category has a strict contract.

Fred SHOULD support 2–3 categories maximum.

### 6.1 Category: GraphAgent

GraphAgent provides a pure graph definition (structural), and the platform compiles it into an executable graph.

Contract:

- AgentDefinition MUST provide `build_graph(spec: GraphSpec) -> GraphDefinition`
- `build_graph` MUST be pure (no I/O)
- The platform compiles the graph during activation or lazily at first run with canonical settings
- Streaming and checkpointing are platform-owned

GraphDefinition MAY be used to produce a preview artifact (Mermaid) without activation.

### 6.2 Category: ReActAgent

ReActAgent provides:

- a system prompt template (tuned fields)
- a tool policy (declared tools + selection constraints)
- optional guardrails

Contract:

- AgentDefinition MUST provide a ReAct policy object (pure)
- The platform provides the ReAct loop and tool router
- The agent MUST NOT implement its own lifecycle, tool session, or checkpointing

Preview MAY describe the loop and tool set (text or DAG).

### 6.3 Category: ProxyAgent

ProxyAgent delegates execution to an external system (HTTP/MCP/queue/etc).

Contract:

- AgentDefinition MUST declare proxy endpoint/transport details as configuration
- Platform activation binds the proxy client and credentials
- Inspection MUST NOT require contacting the proxy target
- Preview MUST be text-only or none

### 6.4 Unsupported patterns

The following are forbidden because they create drift:

- Agents that switch categories at runtime
- Agents whose executable behavior depends on inspection/preview compilation
- Agents that create executable graphs only after activation but still claim to be GraphAgent
  (if runtime-dependent, they must be expressed as ReActAgent or ProxyAgent, or use platform-provided runtime wiring that does not change the graph topology)

## 7. Runtime Lifecycle (Platform-Owned)

Agent authors do not manage lifecycle sequencing.

Fred runtime MUST define exactly two lifecycle phases:

### 7.1 bind(context) phase (cheap, no I/O)

bind phase responsibilities:

- attach RuntimeContext
- rebuild all context-scoped helpers (workspace clients, user-scoped stores, per-session handles)
- prepare runtime-local configuration derived from context

bind MUST NOT perform external I/O.

bind MUST be invoked:

- on fresh runtime creation
- on any runtime reuse when context changes
- on any exchange if context may differ per exchange (policy-driven)

### 7.2 activate() phase (heavy, may do I/O)

activate phase responsibilities:

- initialize models (or model handles)
- initialize MCP sessions/transports/tool registries
- create remote clients, auth sessions, caches
- compile execution artifacts (graph compilation, routers) if not lazy

activate MAY perform external I/O.

activate MUST be invoked:

- exactly once per AgentRuntime instance before first execution
- or lazily on first execution (but only by the platform)

### 7.3 dispose() phase (cleanup)

dispose phase responsibilities:

- close MCP sessions
- close remote clients
- flush metrics/traces
- release resources

dispose MUST be safe to call multiple times (idempotent).

## 8. Execution Contract (Streaming and Invoke)

Fred provides two execution entrypoints:

- `invoke(input, config) -> output`
- `stream(input, config) -> async iterator of events`

Execution semantics are owned by the platform.

### 8.1 Canonical checkpointer and streaming memory

The platform MUST define a canonical checkpointing strategy per runtime:

- either per-session
- or per-exchange
- or disabled

Agents MUST NOT choose checkpointing configuration.
Agents MUST NOT compile graphs with arbitrary checkpointers.

### 8.2 Determinism and reproducibility expectations

Given the same:

- AgentDefinition version
- runtime configuration
- input messages
- tool results

The platform SHOULD provide reproducible execution behavior.
Non-determinism from models is expected; non-determinism from lifecycle ordering is forbidden.

## 9. Caching and Reuse Semantics

Caching is a platform implementation detail, but reuse semantics are contractual.

### 9.1 Behavioral equivalence

For a given AgentDefinition and RuntimeContext, the behavior of:

- reused AgentRuntime
  and
- freshly created AgentRuntime
  MUST be equivalent, modulo expected model nondeterminism and non-deterministic external systems.

This requirement forbids partial refresh semantics that skip rebind.

### 9.2 Cache key policy

The platform MUST define a cache key policy, such as:

- (session_id, agent_id)
- (workspace_id, agent_id)
- (user_id, agent_id)
  or any combination.

The key policy MUST be explicit and documented.

### 9.3 Safety constraints

If an AgentRuntime holds resources that may expire (tokens, sessions, sockets),
the platform MUST:

- validate liveness on reuse, or
- use TTL-based eviction, or
- recreate runtime

## 10. Authoring API (What Agent Authors Implement)

Agent authors implement only:

- metadata and tuning fields
- declared tool requirements
- execution category contract:
  - GraphAgent: `build_graph(...)` and node functions
  - ReActAgent: `policy(...)` (prompt + tools + guardrails)
  - ProxyAgent: `proxy_spec(...)`

Agent authors MUST NOT:

- manually cache compiled graphs
- manage MCP initialization
- manage model clients directly unless explicitly injected by platform in activation
- implement custom lifecycle sequencing

If an agent needs specialized runtime setup, it MUST declare those dependencies so the platform can perform activation.

## 11. Platform Wiring Responsibilities

Fred runtime MUST provide:

- ModelRegistry / ModelProvider resolution
- ToolRegistry / MCP wiring and authorization
- Workspace/storage clients binding
- Execution engine (graph runner or react loop)
- Event streaming and message shaping
- Observability hooks (metrics, tracing, logs)
- Policy enforcement (allowed tools, rate limits, safety constraints)
- Stable inspection endpoint

## 12. Compliance Tests (Required)

Fred MUST maintain a compliance suite that runs in CI.

Minimum required tests per agent definition:

### 12.1 inspection_without_activation

- Build AgentDefinition
- Call inspect_agent(...)
- Assert no activation occurs
- Assert no external I/O occurs (best-effort detection)
- Assert payload includes metadata and tool requirements

### 12.2 runtime_reuse_equivalence

- Create runtime, bind+activate, run a trivial input
- Reuse runtime with refreshed context, bind again, run same trivial input
- Assert invariants:
  - context-scoped helpers were rebound
  - executor exists and runs
  - no stale helpers remain (framework-level checks)

### 12.3 deterministic_compilation_contract

- Ensure compilation semantics do not depend on call order:
  - compile with canonical parameters
  - attempt compile with different parameters
  - assert platform does not silently reuse incorrect artifacts

## 13. Deprecations (Immediate)

The following concepts are deprecated and MUST NOT be used for new agents:

- `_graph` as a meaningful public concept
- `get_graph_mermaid()` as primary inspection
- dual preview mechanisms
- `set_runtime_context()` as a distinct semantic from bind
- agent-side compiled graph caching
- agent-side selection of checkpointer/checkpointing strategy

The platform MAY keep shims temporarily for migration but MUST NOT allow them to define new semantics.

## 14. Compatibility Shims (Allowed Temporarily)

To migrate existing AgentFlow subclasses, the platform MAY provide an adapter that maps:

- old AgentFlow methods
  - bind_runtime_context
  - build_runtime_structure
  - activate_runtime
  - get_compiled_graph
    into
- new platform-owned lifecycle

However:

- adapters MUST enforce Invariants A–E
- adapters MUST not reintroduce semantic ambiguity
- new agents MUST NOT use the old AgentFlow lifecycle surface

## 15. One-Paragraph Summary (Contributor Facing)

An agent is a definition: metadata, fields, tool requirements, and an execution category contract.
Fred owns runtime: binding context, activating dependencies, compiling executors, streaming execution,
inspection, caching, and observability.
Inspection is metadata-first and never activates dependencies.
Runtime reuse must be equivalent to fresh execution for the same context.
Compilation and checkpointing are platform-defined and deterministic.

End of specification.
