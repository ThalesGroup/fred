# RFC: Distributed Agent Architecture — Independent Packaging, Deployment, and Execution

- Status: Draft
- Authors: Fred core team
- Intended audience: Fred maintainers, platform architects, agent authors, DevOps engineers
- Scope: Agent packaging model, deployment architecture, transport protocol, Temporal integration
- Non-goals: LLM provider strategy, agent authoring API design, knowledge-flow architecture

---

## 1. Summary

This RFC proposes a long-term architecture in which Fred agents are **independently packaged, deployed, and registered** — decoupled from the main agentic-backend repository and runtime process.

The ultimate objective is to make it possible for an agent author to:

- create a standalone repository with no dependency on the Fred monorepo,
- declare the Fred agent authoring package(s) as the only framework dependency,
- write and test the agent in isolation,
- publish a Docker image using a standard Fred base image,
- deploy that image independently in Kubernetes,
- have the agent automatically register itself with the Fred platform at startup,
- scale, upgrade, and retire that agent without touching any other service.

This objective requires changes at three layers: **transport**, **packaging**, and **execution**. These layers are addressed together in this RFC because they are interdependent. The transport change unlocks the packaging model. The packaging model unlocks independent deployment. Independent deployment enables Temporal-native long-running and batch agent execution.

---

## 2. Problem Statement

### 2.1 All agents share a process

Today every Fred agent runs inside the agentic-backend process. Adding a new agent requires:

- editing the main repository,
- adding a Python class path to `definition_refs.py`,
- registering the agent in `agents_catalog.yaml`,
- rebuilding and redeploying the entire agentic-backend image.

This couples the release cycle of every agent to the release cycle of the platform. An experimental agent cannot be deployed without a full platform release. A buggy agent can destabilize the entire backend. A resource-intensive agent affects all other agents.

### 2.2 The transport layer creates unnecessary deployment constraints

The current streaming endpoint is a WebSocket (`/agentic/v1/chatbot/query/ws`). WebSocket is a bidirectional protocol that requires special handling at every infrastructure layer: Vite dev proxy (`ws: true`), nginx reverse proxy (timeout and upgrade passthrough configuration), Kubernetes ingress annotations, load balancer sticky sessions.

This infrastructure friction is not inherent to agent streaming — it is a consequence of the protocol choice. It also makes proxying agent execution across pod boundaries significantly more complex than it needs to be.

### 2.3 The registration model is static and centralized

Agent discovery relies on a single `definition_refs.py` file and a YAML catalog maintained in the platform repository. An agent that lives in an external package cannot self-register. There is no protocol for an agent to announce its presence, capabilities, or routing address at runtime.

### 2.4 Temporal is underused for agent execution

Fred already uses Temporal for scheduled tasks. However, conversational agent execution does not use Temporal. This means long-running agents, batch agents, and agents that must survive process restarts have no durable execution model. Every agentic execution is bound to the lifetime of an HTTP or WebSocket connection.

---

## 3. Design Goal

The architecture should allow:

- **independent authoring**: agent authors work in their own repositories with a minimal SDK dependency,
- **independent packaging**: each agent is a pip package and a Docker image, versioned independently,
- **independent deployment**: an agent pod can be deployed, scaled, and retired without touching the platform,
- **independent registration**: agents announce themselves to the platform at startup without requiring static catalog entries,
- **infrastructure transparency**: the streaming transport should work through standard HTTP infrastructure with no special proxy configuration,
- **execution durability**: long-running and batch agents should use Temporal for durable execution, not ephemeral HTTP connections.

---

## 4. Primary Design Principle

> An agent should be a self-contained deployable unit. The platform should discover and route to agents — not contain them.

This shift — from agents-as-classes-in-a-process to agents-as-services — is the central architectural change proposed by this RFC.

---

## 5. Transport Reform: HTTP Streaming Replaces WebSocket

### 5.1 The current model

The WebSocket endpoint combines three concerns:

- receiving user messages (`ChatAskInput`),
- receiving HITL resume responses (`HumanResumeInput`),
- streaming server-to-client events (`StreamEvent`, `AwaitingHumanEvent`, `FinalEvent`, `ErrorEvent`, `SessionEvent`).

These are multiplexed over a single persistent connection with a `while True` receive loop.

### 5.2 The proposed model

Replace the WebSocket endpoint with two plain HTTP streaming endpoints using Server-Sent Events or newline-delimited JSON:

- `POST /chatbot/query/stream` — sends a user question, streams events until `final` or `awaiting_human`,
- `POST /chatbot/resume/stream` — sends a HITL resume payload, streams events until `final` or `awaiting_human`.

The event vocabulary is unchanged. Only the transport changes. Each exchange maps to exactly one HTTP request/response pair. Session continuity is maintained by `session_id`, not by connection lifetime.

### 5.3 Why this matters for the distributed model

HTTP streaming through standard reverse proxies is trivial. The scenario where the agentic-backend proxies execution to a remote agent pod becomes:

```
client → POST /chatbot/query/stream
         → agentic-backend (routes by agent_id)
              → POST agent-pod/execute
              ← chunked streaming response
         ← proxied streaming response to client
```

Every nginx, Kubernetes ingress, CDN, and load balancer handles this correctly without any configuration. There is no WebSocket upgrade, no sticky session, no proxy timeout annotation. This is the primary reason the transport change is a prerequisite for the distributed execution model.

### 5.4 Additional benefits

- Standard `Authorization: Bearer` header on every request — no token-in-message workaround.
- Each exchange is stateless at the connection level — any replica can handle any request.
- SSE `Last-Event-ID` enables client-side resume after connection drop.
- Standard HTTP tooling works for load testing: `k6`, `curl`, `hey`.
- Vite dev proxy works without `ws: true` — the class of infrastructure bug that triggered this RFC disappears.

---

## 6. Packaging Model: Agents as Independent Packages

### 6.1 SDK extraction

The agent authoring API (`GraphAgent`, `GraphWorkflow`, `typed_node`, `StepResult`, step helpers, HITL primitives) is extracted from the agentic-backend into one or more standalone installable packages.

The exact packaging boundary — whether the authoring surface and the runtime implementation are shipped as a single package or as separate packages with an explicit API/implementation split — is an open question addressed in the SDK V2 RFC. What this RFC requires is the outcome: an agent author should be able to depend only on the authoring surface, with no transitive dependency on the agentic-backend codebase.

The authoring package(s) contain:

- authoring abstractions (`GraphAgent`, `GraphWorkflow`, `typed_node`),
- state and contract types,
- step helpers and built-in workflow patterns,
- HITL primitives,
- MCP client interfaces.

They carry no dependency on FastAPI, the session store, the chatbot runtime, or any other platform service.

### 6.2 Agent packages

An agent lives in its own repository. It is a pip-installable package that depends on the Fred authoring package(s). It declares its `agent_id`, `role`, `description`, and capabilities as class-level fields on the `GraphAgent` subclass.

### 6.3 Docker packaging

An agent is packaged as a Docker image using a standard Fred agent worker base image:

```dockerfile
FROM fred-agent-worker:X.Y
RUN <install my-agent-package>
```

The base image provides the worker process, the full runtime, and the registration bootstrap. The agent package provides only the business logic. The exact installation command depends on the package manager and registry choices made when the SDK packaging is finalized.

### 6.4 Self-registration via `__init_subclass__`

When the agent package is imported, the `AgentDefinition` base class registers the agent class in an in-memory registry keyed by `agent_id`. No `definition_refs.py` file, no YAML catalog entry, no static mapping is required. The registry is populated by import alone.

This eliminates the current three-file registration ceremony. Adding a new agent requires only writing the agent class and adding the package to an image.

---

## 7. Deployment Model: Agents as Independent Pods

### 7.1 Agent worker process

Each agent pod runs a lightweight worker process. This process:

- imports the agent package (triggering self-registration),
- starts listening for execution requests from the platform,
- exposes a health endpoint,
- calls the platform registration endpoint at startup.

The worker process is provided by the base image. Agent authors do not implement it.

### 7.2 Registration protocol

Agent registration is a **Control Plane responsibility**. This is consistent with the platform placement rule: the Control Plane API owns all administrative, lifecycle, and catalog concerns. The agentic-backend is a runtime — it should not own a mutable registry of external services.

At startup, the agent pod calls a registration endpoint on the **Control Plane API** with:

- `agent_id`,
- `service_url` (the pod's internal cluster address),
- `capabilities` (supported input types, HITL support, streaming support, Temporal task queue if applicable),
- `version`.

The Control Plane maintains the live agent registry, persists agent metadata, and handles deregistration when health checks fail or a pod shuts down gracefully.

The Control Plane also becomes the source of truth for the agents catalog that the agentic-backend previously owned through `agents_catalog.yaml` and `definition_refs.py`. Static YAML catalog entries are a degenerate case of this registry — they can be pre-seeded at startup by the Control Plane from configuration, while externally deployed agents register dynamically.

### 7.3 Routing

When the agentic-backend receives a request for `agent_id: "BankTransfer"`, it queries the Control Plane registry, obtains the agent's execution endpoint, and proxies the HTTP streaming request. The agentic-backend remains the auth boundary and the session owner. The agent pod handles only execution.

The Control Plane registry is the single source of truth for both in-process agents (registered at agentic-backend startup) and remote agent pods (registered by the pod itself). The routing layer in the agentic-backend is transparent to the client — it does not know or care whether the agent runs in-process or in a remote pod.

---

## 8. Temporal Integration: Durable Execution for Long-Running Agents

### 8.1 The current limitation

All conversational agent executions are bound to an HTTP or WebSocket connection. If the agentic-backend process restarts during execution, the exchange is lost. There is no durable execution for agents that run for more than a few seconds or that require suspension between turns.

### 8.2 Temporal as the execution backbone for durable agents

Fred already uses Temporal for scheduled tasks. The distributed agent model makes Temporal the natural execution backbone for a second category of agents: those that are long-running, stateful across multiple sessions, or batch-oriented.

A Temporal-native agent:

- registers a Temporal workflow instead of (or in addition to) an HTTP execution endpoint,
- maps HITL interrupts to Temporal workflow signals,
- maps agent state to Temporal workflow state (durable, survives process restart),
- maps long-running tool calls to Temporal activities (with retry policies and heartbeats).

The agentic-backend submits a Temporal workflow execution on behalf of the user and then streams the result back as events arrive.

### 8.3 The streaming bridge

Temporal workflows produce intermediate results asynchronously. The streaming bridge between a Temporal workflow and the HTTP streaming response uses a lightweight event queue:

- the Temporal worker publishes delta events to a per-exchange channel (Redis Streams or equivalent),
- the agentic-backend tails that channel and emits SSE events to the client,
- when the workflow completes, the final `FinalEvent` is emitted and the stream closes.

This bridge is entirely internal to the platform. Agent authors write normal `GraphAgent` code. The Temporal runtime is transparent.

### 8.4 What Temporal unlocks

- **Durability**: an agent survives pod restarts, network interruptions, and maintenance windows.
- **Long-running agents**: agents that run for minutes or hours without holding an open connection.
- **Batch agents**: agents triggered by schedules or external events, not by user messages.
- **HITL across sessions**: a workflow can pause for days awaiting human input, then resume cleanly.
- **Retry and compensation**: Temporal's activity retry policies eliminate custom retry logic in agent code.
- **Audit trail**: Temporal's workflow history provides a complete, durable execution log per exchange.

---

## 9. Migration Path

The proposed architecture is introduced incrementally. Each phase is independently valuable and does not block the next.

### Phase 1 — SDK extraction and self-registration

Extract the authoring API into standalone installable package(s), with no agentic-backend dependency. The exact package structure (single package vs. surface/implementation split) is resolved as part of the SDK V2 work. Implement `__init_subclass__` self-registration on `AgentDefinition`. Allow `definition_ref` to accept a dotted class path directly. Eliminate `definition_refs.py` for new agents.

Agents remain in-process. Nothing changes for deployed users.

### Phase 2 — HTTP streaming transport

Add `POST /chatbot/query/stream` and `POST /chatbot/resume/stream` alongside the existing WebSocket endpoint. Migrate the frontend from WebSocket to HTTP streaming. Deprecate the WebSocket endpoint.

Agent execution remains in-process. The transport change enables all subsequent phases.

### Phase 3 — Agent worker base image

Define the `fred-agent-worker` base image and the agent registration protocol. Deploy the first external agent pod (the bank transfer sample is a good candidate). Validate routing, health checking, and in-process/remote agent coexistence.

### Phase 4 — Temporal-native agents

Define the Temporal execution path for durable agents. Implement the streaming bridge. Deploy the first Temporal-native agent. Validate HITL over Temporal signals.

---

## 10. Non-Goals

This RFC does not propose to:

- remove the in-process agent model — it remains valid and efficient for most agents,
- require all agents to use Temporal — conversational agents remain HTTP-native,
- define multi-tenant agent isolation (different organizations hosting agents) — that is a future concern,
- change the agent authoring API — `GraphAgent`, `GraphWorkflow`, and step helpers are unchanged; authoring API design is covered in the SDK V2 RFC,
- redesign the Control Plane beyond adding the agent registry — the existing team/user/policy responsibilities of the Control Plane are unchanged,
- address observability and tracing — that is covered in a separate RFC.

---

## 11. Open Questions

1. Should the Control Plane registry use push (agent pod calls `/register` at startup) or pull (Control Plane actively probes well-known discovery endpoints on each pod)? Push is simpler; pull is more resilient to startup race conditions.
2. What is the correct failure mode when a remote agent pod is unreachable — immediate error, transparent fallback to an in-process instance if one exists, or retry with circuit-breaker?
3. Should the Control Plane registry be purely in-memory (rebuilt on startup from active pods) or persisted (surviving Control Plane restarts)? A hybrid — persisted catalog for static agents, live heartbeat for dynamic pods — may be the right answer.
4. Which agents should be Temporal-native by default, and which should remain HTTP-native? Should agent authors declare an execution hint on the class, or should the platform decide based on execution duration and HITL requirements?
5. What is the versioning contract between the authoring package(s) and the agentic-backend runtime? Which changes in the runtime require a coordinated SDK release?
6. Should the authoring surface and the runtime implementation be separate packages? The SDK V2 RFC is the right place to resolve this, but the decision has direct impact on the base image composition and the dependency graph for agent authors.
7. How should the streaming bridge (Temporal → SSE) handle back-pressure when the client reads slowly?

---

## 12. Proposed Issues

The following issues are proposed to implement this RFC incrementally.

**Transport**

- Replace WebSocket with HTTP streaming endpoint (SSE/NDJSON) for `query` and `resume`
- Migrate frontend from WebSocket to `fetch` streaming
- Deprecate and remove the WebSocket chatbot endpoint

**Packaging**

- Decide the authoring package structure (single package vs. surface/implementation split) — tracked in SDK V2 RFC
- Extract the authoring API into standalone installable package(s) with no agentic-backend dependency
- Implement `__init_subclass__` self-registration on `AgentDefinition`
- Allow `definition_ref` to resolve a dotted class path directly (eliminate `definition_refs.py`)
- Define and publish the `fred-agent-worker` base image

**Deployment and registration (Control Plane)**

- Design and implement the agent registry in the Control Plane API (registration endpoint, health-check deregistration, catalog seeding from YAML)
- Migrate `agents_catalog.yaml` ownership from agentic-backend to Control Plane
- Implement the agent registry query in the agentic-backend (replaces static `AgentManager` catalog load)
- Implement HTTP proxy routing in the agentic-backend for remote agent pods
- Deploy the bank transfer sample as the first external agent pod

**Temporal**

- Define the Temporal-native agent execution contract (workflow, signals, activities)
- Implement the per-exchange streaming bridge (Temporal worker → Redis Stream → SSE)
- Validate HITL over Temporal workflow signals

---

## 13. Recommendation

Proceed with the phases in order. Phase 1 (SDK extraction) and Phase 2 (HTTP streaming) are independent of each other and can be done in parallel. Both are prerequisites for Phase 3. Temporal integration (Phase 4) requires Phase 3 to be stable.

The HTTP streaming change has the highest immediate value: it fixes a class of infrastructure problems, simplifies the dev environment, and unblocks the distributed execution model. It should be the first issue opened and the first merged.

The SDK extraction is the most important long-term investment: it defines the boundary between the platform and the agent authoring ecosystem, and that boundary should be stabilized early.

---

## 14. Final Statement

The goal of this architecture is not to add complexity. The goal is to remove the artificial coupling between agent authoring, platform release cycles, and runtime process boundaries.

When an agent author can write, package, deploy, and operate their agent as an independent unit — using only the SDK and a base image — Fred becomes a platform that agents run on rather than a codebase that agents live inside.

That is the right boundary for an industrial-grade agent platform.
