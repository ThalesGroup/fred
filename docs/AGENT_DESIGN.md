# Design Note - Tool Capabilities, Governance, and HITL in Fred

## Purpose

This note consolidates the current Fred design for:

- tool-capable agents (local tools, MCP tools, long-running jobs),
- governance (approval, policy, permissions),
- Human-in-the-Loop (HITL),
- and the roadmap toward a reusable, platform-level pattern.

It is intended as a precise reference for the dev team and as a discussion base for the next design step.

In practice, this problem is often solved: 
- ad-hoc,
- differently in every agent,
- using brittle heuristics (string parsing, regex, keywords),
- or by embedding implicit logic inside prompts.

- duplicated logic,
- inconsistent UX,
- poor auditability,
- difficult security reviews,
- and fragile behavior as capabilities grow.

---

## Terminology (Important)

This distinction is central to the current and future design.

### Capability

A capability is **what the agent can do**:

- "web + GitHub read-only inspection"
- "postal business actions"
- "IoT tracking diagnostics"
- "corpus search"

A capability typically exposes one or more tools.

### Tool

A tool is the executable unit seen by the LLM / LangChain:

- `github_read_readme`
- `reroute_package_to_pickup_point`
- `track_package`

### Connector (catalog entry)

A connector is a configured entry that makes a capability available to agents.

Today this is represented in the "MCP" catalog UI, but conceptually it already includes:

- **remote MCP endpoints**
- **local in-process providers**

### Transport / Provider

Transport is **how** a capability is reached:

- `streamable_http`, `stdio`, `websocket`, ...
- `inprocess` (local provider inside `agentic-backend`)

Key principle:

> **Capability is the product abstraction. Transport is an implementation detail.**

---

## What Exists Today in Fred (Current State)

### 1. Agent Runtime and Tool Resolution

Fred currently resolves tools through `MCPRuntime`, which now supports:

- remote MCP servers (traditional MCP transports)
- local in-process providers (`transport = "inprocess"`, `provider = ...`)

This gives a unified runtime outcome:

- `list[BaseTool]` for the agent

This is the right runtime shape because it stays close to LangChain/LangGraph.

### 2. Generic Tool Agent: `BasicReActAgent`

`BasicReActAgent` is Fred's generic dynamic tool agent.

It currently provides:

- tool-aware system prompt construction
- shared Mermaid rendering prompt policy injection
- MCP/local tool resolution through `MCPRuntime`
- optional tool-level HITL approval gating
- fallback path when `langchain.agents.create_agent` is unavailable

It is intentionally pragmatic and useful for:

- dynamic agents created in UI
- demos and exploratory assistants
- broad tool access with basic governance

### 3. Shared HITL Tool Approval Policy (Refactored)

Tool-level HITL policy logic has been extracted from `BasicReActAgent` into a shared module:

- `agentic_backend/core/interrupts/tool_approval.py`

This shared module now covers:

- tuning fields (`safety.enable_tool_approval`, `safety.approval_required_tools`)
- read-only vs mutating prefix classification
- exact-name approval rules
- localized HITL policy text (FR/EN)
- localized HITL card payloads (FR/EN)

This is an important architectural improvement:

- policy logic is reusable,
- `BasicReActAgent` keeps orchestration glue,
- behavior remains unchanged.

### 4. HITL i18n (Shared)

Localized HITL payload selection is handled in:

- `agentic_backend/core/interrupts/hitl_i18n.py`

This allows HITL cards to follow `runtime_context.language` consistently across agents.

### 5. Reusable Gated Tool Loop

Fred has a reusable LangGraph helper:

- `agentic_backend/core/tools/tool_loop.py` -> `build_tool_loop(...)`

It provides:

- reasoning node (LLM)
- conditional tool execution
- optional HITL gating callback per tool
- optional post-processing

This is the right level for reuse across ReAct-like agents.

### 6. Business Workflow Agents (Explicit Graphs)

Fred also supports explicit LangGraph business agents, for example:

- `LaPosteDemoAgent`

These agents implement:

- deterministic multi-step workflows
- domain-specific decisions
- domain-specific HITL cards (choice UIs, not just "approve tool call")

This pattern is preferable for:

- business-critical flows
- demos requiring reliability and explainability
- governed workflows with clear branching and user approvals

---

## What LangChain / LangGraph Provide (and What They Do Not)

### LangChain Tool Calling / Function Calling

Provides:

- structured tool selection and arguments

Does not provide:

- governance / policy enforcement
- HITL policy semantics
- permission model
- cost/risk policy
- "suggest vs execute" separation

### LangGraph ToolNode

Provides:

- execution orchestration in a graph

Does not provide:

- approval gates by policy
- platform governance
- policy outcomes / audit model

### LangChain HITL Middleware

Provides:

- a mechanism to intercept tool calls and request approval

Does not provide:

- platform-level policy architecture
- planner/policy/executor decomposition
- Fred-specific orchestration semantics (Temporal, custom resumes, multi-source tools)

### ReAct Agents (LangChain-style)

Position in Fred (clarified):

- **Not the final platform architecture for governed workflows**
- **Still useful as a practical generic agent pattern**, especially when augmented with:
  - tool restrictions
  - shared HITL approval policy
  - shared prompt policies
  - runtime tool resolution

So the correct stance is:

> ReAct is acceptable as a generic agent strategy, but it is not sufficient as the platform governance architecture.

---

## Current Design Pattern in Fred (Operational View)

Today, Fred effectively operates with two layers of governance:

### A. Tool-level governance (generic)

Used by generic tool agents (e.g. `BasicReActAgent`):

- LLM selects tool call
- deterministic policy decides if tool requires approval
- system raises `interrupt(...)` if needed
- user approves/cancels
- tool executes or agent replans

This gives immediate value with low integration cost.

### B. Workflow-level governance (domain-specific)

Used by explicit business agents (e.g. La Poste demo):

- agent computes options / diagnosis
- business logic decides when to present a user choice
- agent raises a domain-specific `interrupt(...)` payload
- user chooses a branch (reroute / reschedule / cancel)
- workflow continues deterministically

This gives stronger UX and control for business processes.

---

## The Target Architectural Decomposition (Platform-Level)

The long-term reusable pattern should be explicit and shared:

### 1. Planner (LLM-driven decision proposal)

Responsibility:

- analyze user request, conversation, and available capabilities
- propose one of:
  - answer directly
  - ask clarification
  - call a capability/tool with arguments

Properties:

- structured output (schema / tool call / Pydantic)
- proposal only, no execution

### 2. Policy (deterministic governance)

Responsibility:

- decide whether proposal is:
  - allowed,
  - denied,
  - requires clarification,
  - requires approval (HITL),
  - requires escalation / async execution

Properties:

- deterministic
- auditable
- configurable
- no LLM required

### 3. Executor (tool/capability execution)

Responsibility:

- execute approved actions against:
  - local tools
  - MCP tools
  - long-running jobs

Properties:

- no decision-making
- no policy inference
- execution + observability

### 4. State Orchestrator (LangGraph)

Responsibility:

- compose Planner / Policy / Executor in a reusable graph
- persist state
- handle interrupts/resume
- support long-running branches

This is where LangGraph shines.

---

## How HITL Fits (Cleanly)

HITL is a policy outcome, not a separate architecture.

Canonical flow:

1. Planner proposes action
2. Policy evaluates action
3. If `requires_approval`:
   - emit `interrupt(...)`
4. User decision resumes graph
5. Executor runs or cancels

This avoids:

- duplicating confirmation text per agent,
- mixing governance with LLM prompting,
- inconsistent approval behavior.

Important nuance:

- **tool approval HITL** (generic) and
- **business choice HITL** (domain-specific)

both use `interrupt(...)`, but they come from different policy layers and should not be conflated.

---

## Where We Are Strong Today

Fred already has a good foundation:

- shared HITL approval policy extraction (`tool_approval.py`)
- shared HITL i18n (`hitl_i18n.py`)
- reusable gated tool loop (`build_tool_loop`)
- unified runtime tool resolution for remote MCP + local in-process providers
- explicit business workflow agents for deterministic demos/use-cases

This is a solid, practical design trajectory.

---

## Gaps / Tensions (Current)

### 1. MCP catalog vs Capability catalog (abstraction mismatch)

Today the UI uses an "MCP" catalog to expose both:

- true MCP endpoints
- local in-process capabilities

This is acceptable as a transitional step, but the naming is conceptually misleading.

Target abstraction should be:

- **Capability catalog** (what it enables)
- with provider/transport metadata (`mcp`, `inprocess`, ...)

### 2. Tool decision logic is still partially agent-local

Generic agents still rely on:

- LLM tool selection
- prompt guidance
- optional HITL policy

This is useful, but not yet the fully centralized Planner/Policy/Executor pattern.

### 3. Governance is split between generic and business agents (intentionally, but not formalized)

This is not wrong, but the framework should make the distinction explicit:

- generic tool approval policy
- workflow/business policy

---

## Recommended Next Design Move (Team Discussion)

### Next Move: Introduce a Capability-First Catalog and Resolver

This is the highest-leverage next step because it improves both:

- developer ergonomics
- conceptual clarity

without forcing an immediate rewrite of agent logic.

#### Goal

Replace transport-first thinking ("MCP servers") with capability-first thinking:

- "Web + GitHub read-only"
- "Postal business demo"
- "IoT tracking demo"
- "Corpus search"

Each capability then declares how it is delivered:

- provider kind: `mcp`, `local`
- transport (if applicable): `streamable_http`, `stdio`, `inprocess`, ...

#### Why this should be next

- It aligns UI and backend on the right abstraction.
- It avoids local capabilities pretending to be MCP forever.
- It simplifies future governance and policy assignment per capability.
- It prepares the Planner/Policy/Executor architecture.

#### What can stay unchanged initially

- `MCPRuntime` can remain the runtime resolver (internally extended/refined).
- Agents can still receive `list[BaseTool]`.
- `BasicReActAgent` can continue to work unchanged at behavior level.

#### Team discussion questions

1. Do we agree on **Capability** as the primary abstraction for agent configuration?
2. Should the current "MCP Hub" be evolved into a **Tool/Capability Connectors** page (UI rename first, model later)?
3. What minimal capability metadata do we standardize first?
   - id
   - display name
   - description
   - provider kind (`mcp`/`local`)
   - transport
   - read-only / mutating hint
   - tool names (optional preview)

---

## Possible Follow-up Move (After Capability Catalog)

Once capability modeling is in place, the next major step is:

### Shared Governed Tool Decision Subgraph

A reusable LangGraph subgraph (or helper) that formalizes:

- planner proposal
- policy evaluation
- HITL outcome
- executor dispatch

This would become the platform-standard path for governed tool usage, while still allowing:

- simple generic ReAct agents
- explicit business agents with custom flows

---

## Practical Guidance for Agent Authors (Current Best Practice)

### Use `BasicReActAgent` (or similar generic tool agent) when

- you need rapid iteration
- tools are relatively safe or approval-gated
- behavior can be LLM-driven
- exact workflow determinism is not required

### Use an explicit LangGraph business agent when

- workflow steps must be deterministic
- domain-specific HITL choices are part of UX
- approvals/branches must be explicit
- demo reliability or production governance is critical

### Always prefer shared policy helpers for governance

Do not duplicate:

- approval heuristics
- HITL payload patterns
- language selection logic

Reuse shared modules and extend them centrally.

---

## Non-Goals (For This Design Note)

This note does not define:

- a full authorization/permissions model
- cost accounting schemas
- final audit event schema
- planner prompt implementation details
- Temporal orchestration conventions

These should be documented separately once the capability model is formalized.

---

## Proposed ADRs to Create

To reduce ambiguity, the team should consider creating short ADRs for:

1. **Capability-first catalog** (replaces transport-first MCP mental model)
2. **Planner/Policy/Executor decomposition** for governed tool usage
3. **Generic HITL vs business HITL** separation
4. **ReAct role in Fred** (acceptable for generic agents, not the final governance architecture)

---

## Summary

Fred is already on a strong path:

- practical generic agents exist,
- business agents can be deterministic,
- HITL is reusable and localized,
- local and remote tools are converging at runtime.

The next strategic step is to make the **capability abstraction explicit**, then formalize a shared governed decision subgraph on top of it.

