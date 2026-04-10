# Temporal + LangGraph: when to use what

Before discussing our guide and specification to combine the temporal orchestrator with langraph agents, 
it is important to understand the two broad approaches that can be followed: 

## When a single “run LangGraph” activity is the right choice

Use one Activity that runs the whole LangGraph execution if most of the following are true:

- You don’t need step-level retry semantics
- If the agent fails, you are fine retrying the whole run (or handling it in-agent).
- Partial completion does not create costly side effects.
- You mainly need progress for UX, not for correctness
- You can tolerate “best effort” progress updates.
- You don’t need Temporal to be the source of truth for each business milestone.
- The graph is highly dynamic
- Tool calls and branching are determined at runtime by the LLM.
- Decomposing into deterministic workflow steps would either be artificial or would replicate LangGraph inside Temporal.
- You have idempotent external effects
- Writes to DB / object store are idempotent (or properly keyed), so reruns are safe.

In that model: Temporal gives you queueing, timeouts, retries, cancellation, and durability; LangGraph remains the internal orchestrator.

We decided to leverage that pattern first for most of our agents. 

## When multiple smaller activities is the better choice

Decompose into multiple activities (Temporal orchestrates, LangGraph becomes a library or a step engine) if you need any of the following:

- Strong reliability and isolation per phase
    - Example phases: “ingest documents”, “vectorize”, “retrieve”, “draft”, “validate”, “publish artifact”.
    - You want independent retries and backoff per phase.
- Durable checkpoints
    - You want to resume after worker redeployments without redoing expensive work.
    - You want to persist intermediate outputs as first-class artifacts.

- Operational visibility and SLAs
    - You want Temporal visibility to show “stuck in vectorization” vs “stuck in LLM call”.
    - You want per-step metrics, per-step timeouts, and per-step alerting.

- Human-in-the-loop or asynchronous dependencies
    - Waiting for approvals, waiting for external batch jobs, waiting for data availability.
    - Temporal excels here; a monolithic activity is awkward.

- Precise cancellation
    - Cancel only the current step, or stop after the next safe checkpoint.
    - With a monolithic activity, cancellation responsiveness depends on your internal loop.

In that model: Temporal is the real business orchestrator; LangGraph is either:

- used inside some activities (e.g., “draft answer” activity runs a small graph), or
- replaced by explicit workflow logic for the stable parts.

We decided to leverage this pattern to desin applications (and not agents). For example a valiation application that will trigger
agents as part of long running validation campaigns. 

---


## Temporal × Agent Development Rules (Fred)

### 1. Scope and goals

This document defines mandatory engineering rules for implementing long-running agents (LangGraph-based) executed under Temporal in Fred.

Primary goals:

- Ensure Temporal correctness (workflow determinism, replay safety).
- Keep agents free of Temporal dependencies (agent portability).
- Provide production-grade progress reporting and Human-in-the-Loop (HITL).
- Define stable, versioned contracts between UI ↔ backend ↔ scheduler ↔ agents.
- Make retries and restarts safe via idempotency and checkpoints.

Non-goals:

- This document does not prescribe the internal reasoning strategy of agents (prompting, RAG approach).
- It does not define UI specifics; it defines event contracts the UI can consume.

---

### 2. Non-negotiable Temporal rules

#### 2.1 Workflow determinism
Never perform non-deterministic work in a Temporal Workflow.

Workflows MUST NOT:
- Call LLMs, MCP servers, HTTP APIs, databases.
- Read/write files, object stores, or networks.
- Use random values, system time, UUID generation (unless via Temporal APIs).
- Use standard runtime sleep.
- Perform non-deterministic concurrency.

Workflows MAY:
- Orchestrate activities.
- Maintain deterministic state.
- Wait for Signals or Updates.
- Expose Queries.
- Start child workflows if required.

#### 2.2 Activities are the only place for I/O and agent execution
 All non-deterministic work MUST be implemented as Activities:
 - LangGraph / LangChain execution
 - LLM, tool, retriever, embedding calls
 - Database access (SQLite in dev, PostgreSQL in prod, OpenSearch if enabled)
 - Object storage (MinIO/S3)
 - CPU-heavy processing

#### 2.3 Timeouts and retries are mandatory
All Activities MUST define:
- Timeouts
- Retry policies
- Non-retryable error classes

#### 2.4 Heartbeats
Long-running Activities MUST heartbeat regularly to:
- Support cancellation
- Avoid duplicate execution
- Provide liveness signals

---

### 3. Architectural boundary

#### 3.1 Layer separation

**Agent layer**
- Contains LangGraph logic and business reasoning.
- Emits typed AgentEvents.
- Has no Temporal imports or assumptions.

**Temporal adapter layer**
- Owns workflows and activities.
- Handles retries, durability, HITL waiting.
- Translates AgentEvents to workflow state and optional streaming.

**API / UI layer**
- Starts workflows.
- Queries progress.
- Submits human input.
- Fetches artifacts by reference.

#### 3.2 No orchestration semantics in chat messages
AIMessage and response metadata are for display only.
They MUST NOT be used as the control plane for progress or orchestration.

---

### 4. Contracts (typed and versioned)

#### 4.1 AgentInput
Agents receive a versioned domain input model, not framework types.

Minimum fields:
- input_version
- task_id
- user_id
- request_text
- context_refs (session, profile, project, tags, document_uids)
- parameters

Large payloads MUST be passed by reference.

#### 4.2 AgentEvent
All progress and intermediate outputs are expressed as AgentEvents.

Recommended variants:
- ProgressEvent (phase, step, percent, label, timestamp)
- LogEvent (level, message, context)
- ArtifactEvent (artifact_kind, ref, title, mime_type, preview)
- HumanInputRequestEvent (interaction_id, prompt, input_schema, ui_hints, context)
- ErrorEvent (error_code, retryable, message, details)

Events MUST be serializable and size-bounded.

#### 4.3 AgentResult
Activity return type:
- status: COMPLETED | BLOCKED | FAILED
- final_summary
- artifacts
- checkpoint_ref
- blocked (if BLOCKED)
- metrics
- result_version

Large outputs MUST be externalized.

---

### 5. Human-in-the-Loop (HITL)

#### 5.1 No waiting in Activities
Activities MUST NOT wait for humans.
They return status=BLOCKED with:
- interaction_id
- prompt
- input_schema
- checkpoint_ref

#### 5.2 Workflow wait
Workflow MUST wait deterministically using:
- Update handler (preferred)
- or Signal

#### 5.3 Resume
Workflow resumes by calling the agent Activity again with:
- checkpoint_ref
- human_input payload
- referenced attachments

Resumption MUST be idempotent.

---

### 6. Checkpoints and idempotency

#### 6.1 Idempotency
All external side effects MUST be idempotent using deterministic keys:
- task_id + artifact_kind + step/attempt
or equivalent.

#### 6.2 Checkpoints
Agents that can block or run long MUST persist checkpoints externally.
Checkpoint references MUST be versioned and migrateable.

Never rely on in-memory state surviving retries.

---

### 7. Progress reporting

#### 7.1 Progress snapshot
Workflow MUST maintain a ProgressSnapshot and expose Query:
- get_progress()

Snapshot includes:
- status
- phase / step / percent / label
- blocked info
- artifact references
- last update timestamp

### 7.2 Streaming
Near-real-time streaming (WebSocket/pubsub) is an integration concern:
- Consume AgentEvents outside Temporal.
- Temporal remains the source of truth.

---

## 8. LangChain / LangGraph callbacks

### 8.1 Purpose
Callbacks MAY be used for technical observability:
- Tool start/end/error
- LLM tokens and timing
- Retriever activity

### 8.2 Constraints
Callbacks MUST emit AgentEvents via an EventSink.
Callbacks MUST NOT call Temporal APIs directly.

Business progress MUST remain explicit in agent code.

---

## 9. Error taxonomy and retries

### 9.1 Error classes
Define clear error categories:
- InvalidInputError (non-retryable)
- ToolTransientError (retryable)
- RateLimitedError (retryable with backoff)
- ModelProviderError
- HumanRejectedError (non-retryable)
- PersistenceConflictError

### 9.2 Terminal states
Workflows MUST end in:
- COMPLETED
- FAILED
- CANCELED

BLOCKED is not terminal.

---

## 10. Security rules

### 10.1 Untrusted content
All event content is untrusted:
- Escape/sanitize in UI.
- Never emit secrets or credentials.

### 10.2 Authorization
Document and artifact references MUST be authorized.
Agents MUST NOT assume unrestricted access.

---

## 11. Testing requirements

### 11.1 Agent tests
- Test agent logic without Temporal.
- Validate event sequences.
- Test BLOCKED → resume paths.

### 11.2 Workflow tests
- Validate progress queries.
- Validate HITL unblock via Update/Signal.
- Validate retries and cancellation.

### 11.3 API tests
- Start workflow
- Query progress
- Submit HITL input
- Fetch artifacts

---

## 12. Code review checklist

Temporal:
- No I/O in workflows
- Activities only for non-determinism
- Timeouts, retries, heartbeats

Contracts:
- Typed and versioned
- No framework types in contracts
- No orchestration in AIMessage metadata

HITL:
- BLOCKED returned by Activity
- Workflow waits deterministically
- Resume is idempotent

Security:
- No secrets
- Authorization enforced

---

## 13. Guidance for Codex usage

Codex MAY:
- Implement activities/workflows per this document
- Generate Pydantic models and adapters
- Implement callback handlers
- Scaffold tests

Codex MUST NOT:
- Decide workflow vs activity boundaries
- Design new event semantics without review
- Introduce framework types into domain contracts
- Implement HITL via polling or sleeping

All Codex-generated Temporal code MUST be reviewed against this document.

---

## 14. Reference workflow shape

1. Activity: prepare_inputs
2. Loop:
   - Activity: run_agent_until_blocked
   - If BLOCKED: wait Update/Signal
3. Activity: persist_results
4. Return WorkflowResult

---
