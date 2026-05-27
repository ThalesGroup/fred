# Swift Architecture — Independent Agentic Pods

> **Status: Work in Progress.**  
> This document describes the target architecture being built on this branch.
> The existing `agentic-backend` and `knowledge-flow-backend` remain fully operational throughout the migration.
> See [`docs/backlog/BACKLOG.md`](./backlog/BACKLOG.md) for phase status and [`docs/WORKPLAN.md`](./WORKPLAN.md) for current sprint assignments.

---

## The Core Idea

The fundamental shift in this architecture is:

> **An agent pod is a self-contained service. The platform discovers and routes to pods — it does not contain them.**

In the current `agentic-backend` model every agent is a Python class loaded into a single process. Adding a new agent means editing the monorepo, rebuilding, and redeploying the whole backend.

In the Swift model an **agentic pod** is a standalone HTTP service that declares its agents via a simple API. The control plane discovers it, enrolls its agents, and routes execution requests to it. Pod authors work in their own repository with no dependency on the Fred monorepo.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Browser / CLI                                                              │
│  React frontend  ·  fred-agents-cli                                         │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  control-plane-backend  (apps/control-plane-backend)                        │
│                                                                             │
│  • team / user / RBAC management                                            │
│  • agent enrollment registry (which pod exposes which agent)                │
│  • session store and metadata                                               │
│  • product/admin APIs consumed by the frontend                              │
│  • pod registration: maps agent_instance_id → pod URL                      │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ HTTP proxy / direct call
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Agentic Pod  (any conforming HTTP service)                                 │
│                                                                             │
│  Example: apps/fred-agents  (built on libs/fred-runtime)                   │
│  Example: a third-party pod that speaks the same protocol                  │
│                                                                             │
│  GET  <base>/agents                        — agent catalog                 │
│  POST <base>/agents/execute                — blocking execution             │
│  POST <base>/agents/execute/stream         — SSE streaming                  │
│  GET  <base>/agents/sessions/{id}/messages — history                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Agentic Pod Contract

A pod is any HTTP service that implements these four endpoints.  
The Fred `fred-runtime` library implements them out of the box; a third-party pod can implement them independently.

| Endpoint                                     | Purpose                                                                                                                         |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `GET /agents`                                | Returns the catalog: list of agent descriptors with `id`, `name`, `description`, `kind`, `default_tuning` (fields, MCP servers) |
| `POST /agents/execute`                       | Blocking execution — returns `{content, session_id, …}`                                                                         |
| `POST /agents/execute/stream`                | SSE streaming — emits `delta`, `tool_call`, `tool_result`, `final`, `error` frames                                              |
| `GET /agents/sessions/{session_id}/messages` | Conversation history for resume and display                                                                                     |

Full on-wire details: [`libs/docs/ops/AGENT_POD_RUNTIME_PROTOCOL.md`](../libs/docs/ops/AGENT_POD_RUNTIME_PROTOCOL.md)

---

## Registering a New Pod

A pod is registered in `control-plane-backend` via a **product entry** that maps a logical agent instance to a pod URL.

### First-party pod (apps/fred-agents)

`apps/control-plane-backend/control_plane_backend/config/` already wires `fred-agents` as the default pod. The pod URL is resolved from environment config (`FRED_AGENTS_BASE_URL` or equivalent).

### Third-party pod

1. Deploy the pod at a reachable URL (e.g. `https://my-domain/my-agents/v1`).
2. Ensure it exposes `GET /agents` returning a valid catalog.
3. Register it in `control-plane-backend`:
   - Add a `ProductEntry` (or equivalent) mapping `agent_instance_id` → pod URL.
   - The control plane will forward `execute` and `stream` calls to that URL, injecting the user's JWT as `Authorization: Bearer`.
4. The frontend and CLI discover the agent automatically through the control-plane product API — no frontend change needed.

> Automatic Kubernetes-native pod discovery (via labels/annotations) is defined in [`docs/rfc/AGENTIC-POD-RFC.md`](./rfc/AGENTIC-POD-RFC.md) but is **not yet implemented**.  
> Until then, pod URLs are configured manually.

---

## Building a Pod with fred-runtime

The fastest path is `libs/fred-runtime` + `libs/fred-sdk`:

```python
# my_pod/app.py
from fred_runtime.app.agent_app import build_agent_app
from fred_sdk.graph.graph_agent import GraphAgent

app = build_agent_app(agents=[MyAgent()])
```

`build_agent_app` mounts all four protocol endpoints, wires checkpointing, KPI, Langfuse tracing, and an optional CLI. See the [bootstrap guide](./authoring/BOOTSTRAP.md) and [`apps/fred-agents`](../apps/fred-agents/) as a working reference.

The pod can also be a completely independent service in any language — `fred-runtime` is a convenience, not a requirement.

---

## Agent Catalog and MCP Config Fields

When the control plane calls `GET /agents` on a pod, each agent descriptor may include:

- `default_tuning.fields` — agent-level tunable parameters (e.g. `max_tokens`, `temperature`)
- `available_mcp_servers` — list of MCP servers the agent can activate, each with:
  - `id`, `display_name`, `description`
  - `config_fields` — server-level parameters the operator can configure per agent instance (e.g. `search_policy`, `rag_scope`)

The control plane stores these in the **agent instance** record. The frontend `AgentFormModal` surfaces them as the **Tools** tab (server toggle + sub-form for config fields). The CLI `/inspect` command shows the same structure.

---

## What Is and Is Not Done

| Area                                                     | Status                                                      |
| -------------------------------------------------------- | ----------------------------------------------------------- |
| `fred-sdk` agent authoring (v2 graph agents)             | ✅ Production-ready                                         |
| `fred-runtime` pod factory and SSE protocol              | ✅ Production-ready                                         |
| `apps/fred-agents` first-party pod                       | ✅ Replaces `agentic-backend` execution                     |
| `apps/control-plane-backend` product/session APIs        | ✅ Functional, in active development                        |
| Frontend agent management UI (create / edit / tools tab) | ✅ Functional on this branch                                |
| Manual pod URL registration                              | ✅ Works today                                              |
| Automatic Kubernetes pod discovery (labels/annotations)  | ⏳ RFC written, not implemented                             |
| Third-party pod documentation and contract stabilization | ⏳ In progress                                              |
| `agentic-backend` retirement                             | ⏳ Blocked on full frontend migration (see backlog Phase 4) |
| `knowledge-flow-backend` migration to `apps/`            | ⏳ Planned, not started                                     |

---

## Relationship to `develop` — Not a Merge

`swift` is **not** a branch that will simply be merged back into `develop`.

The two branches have diverged too far for a classical `git merge` to be meaningful or safe. More importantly, `swift` is held to a higher standard than `develop`: stricter typing, offline-first tests, frozen execution contracts, and a decoupled architecture that `develop` was never designed for. Pulling `develop` changes in wholesale would undo that work.

The intended migration strategy is **selective, deliberate, and feature-by-feature**:

- Features that are stable and contract-aligned in `swift` will be **cherry-picked or re-implemented** in `develop` (or vice versa) one at a time, with explicit review.
- The `agentic-backend` code in `develop` will progressively be **replaced** by `apps/fred-agents` + `apps/control-plane-backend`, not merged with them.
- Where `develop` carries product features not yet on `swift`, those will be **ported forward** as discrete tasks, not rebased in bulk.
- The goal is for `swift` to become the new `main` once the migration phases are complete — at that point `develop` is retired, not merged.

This means: **do not open a PR from `develop` into `swift`**. If you want to bring a specific commit or feature across, discuss it first and port it as a targeted change. The migration sequencing is tracked in [`docs/backlog/BACKLOG.md`](./backlog/BACKLOG.md).

---

## Key References

| Document                                                                                        | What it covers                                                            |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [`docs/rfc/DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md`](./rfc/DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md) | Original architecture RFC — motivation, transport reform, packaging model |
| [`docs/rfc/AGENTIC-POD-RFC.md`](./rfc/AGENTIC-POD-RFC.md)                                       | Fred Runtime Discovery Contract (FRDC) — Kubernetes-native pod discovery  |
| [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./design/RUNTIME-EXECUTION-CONTRACT.md)           | Frozen execution contract — SSE framing, request/response shapes          |
| [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./design/CONTROL-PLANE-PRODUCT-CONTRACT.md)   | Control-plane product/session/admin API boundaries                        |
| [`libs/docs/ops/AGENT_POD_RUNTIME_PROTOCOL.md`](../libs/docs/ops/AGENT_POD_RUNTIME_PROTOCOL.md) | On-wire protocol reference for pod implementers                           |
| [`docs/backlog/BACKLOG.md`](./backlog/BACKLOG.md)                                               | Migration phases 0–6 and current status                                   |
| [`docs/WORKPLAN.md`](./WORKPLAN.md)                                                             | Current sprint assignments                                                |
| [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./platform/PLATFORM_RUNTIME_MAP.md)                   | Canonical map of which component owns what                                |
