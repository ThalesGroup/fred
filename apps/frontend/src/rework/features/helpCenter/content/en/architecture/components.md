---
title: Components
order: 10
description: The role and responsibilities of each service and shared library.
icon: widgets
---

# Components

The platform is a set of independently deployable services (`apps/`) and shared
libraries (`libs/`).

## frontend

`apps/frontend` — React SPA. Agent catalog, chat UI, session management. It
consumes the `control-plane` and `knowledge-flow` APIs, and opens the execution
stream (SSE) directly to the agent pods.

## control-plane-backend

`apps/control-plane-backend` — the centralized management service. It owns:

- **teams**, **agent instances**, **sessions**, **prompts** and metadata;
- agent pod **discovery and enrollment**;
- execution resolution via `prepare-execution`: it determines **which pod serves
  which agent instance** and returns an ingress-relative URL + the session
  context — **without issuing any capability** (see
  [Security](/help/en/architecture/security));
- **governance** enforcement (model, tool/MCP, prompt, data-scope policies).

It also runs a `Temporal` worker for its background tasks.

> **Pod discovery (current state).** Pods are registered via a static
> `runtime_catalog_sources` list in `control-plane-backend`.

## knowledge-flow-backend

`apps/knowledge-flow-backend` — the long-running data operations:

- **document ingestion**, across three processing profiles (`fast`, `medium`,
  `rich`);
- **vector retrieval** for RAG (index in `OpenSearch`);
- durable execution on **`Temporal` workflows** (ingestion jobs, lifecycle
  tasks).

## Agentic pods

Agent pods run the agent logic. They are all treated identically by
`control-plane` and by ingress routing.

- **`fred-agents`** (`apps/fred-agents`) — the bundled pod: `general`, `rag`,
  `sql`, `sentinel` capabilities, a test harness, OpenAI compatibility. Built on
  `fred-runtime` + `fred-sdk`.
- **`custom-agent-pod`** — a team-provided pod: any agent logic, any tools, any
  model provider. The team imports `fred-runtime` + `fred-sdk`, deploys a
  standard container, and registers it in `runtime_catalog_sources`.

Each pod **authenticates and authorizes** every request itself (see
[Security](/help/en/architecture/security)).

## Shared libraries

- **`fred-runtime`** (`libs/fred-runtime`) — the execution engine: the agent
  loop (ReAct / Deep) on `LangGraph`, the `MCP` client, HITL (human-in-the-loop),
  and the pod's `agent_app`.
- **`fred-sdk`** (`libs/fred-sdk`) — the execution contracts and OpenAI
  compatibility. This is the surface a `custom-agent-pod` imports to conform to
  the managed path.
- **`fred-core`** (`libs/fred-core`) — the shared common core.
- **Capabilities** — `libs/fred-capability-writable-document`,
  `libs/fred-capability-ppt-filler`: packaged capabilities grafted onto agents.

## The pod extensibility model

A team builds its pod by importing `fred-runtime` + `fred-sdk`. Once the pod is
deployed and its `base_url` + `runtime_id` are added to
`runtime_catalog_sources`, `control-plane` enrolls it and the ingress gains a
`/runtime/{runtime_id}/` route. Agents therefore live **outside the monorepo**,
which decouples their lifecycle from the platform's.
