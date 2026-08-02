---
title: Overview
order: 0
description: The platform's logical architecture, components, and the execution flow of a request.
icon: architecture
---

# Technical architecture

This section describes the platform's **logical architecture**: the components,
their responsibilities, how they communicate, and the security model that ties
them together.

> **Intended audience.** Unlike the rest of this help center, this section is
> written for technical profiles — IT engineers, architects, data scientists,
> developers. The vocabulary is precise and components are referred to by their
> original names (`control-plane`, `knowledge-flow`, `fred-agents`, `OpenFGA`,
> `Keycloak`…).

## Logical view

The platform breaks down into four planes, from the client browser to the data
stores:

```mermaid
flowchart TB
  FE["frontend (React SPA)"]

  subgraph plane["Application plane"]
    CP["control-plane-backend"]
    KF["knowledge-flow-backend"]
  end

  subgraph runtime["Agent runtime layer"]
    FA["fred-agents (bundled pod)"]
    CA["custom-agent-pod (team-provided)"]
  end

  subgraph infra["Data stores"]
    PG["PostgreSQL"]
    OS["OpenSearch"]
    OBJ["Object storage (S3)"]
    TMP["Temporal"]
    FGA["OpenFGA"]
    KC["Keycloak"]
  end

  LLM["LLM APIs (external)"]

  FE --> CP
  FE --> KF
  FE -->|"SSE, JWT"| FA
  FE -->|"SSE, JWT"| CA
  CP --> PG
  CP --> FGA
  KF --> OS
  KF --> OBJ
  KF --> TMP
  FA --> LLM
  CA --> LLM
  FA --> PG
```

- The **frontend** talks to `control-plane` and `knowledge-flow` for everything
  catalog-, session- and document-related; it opens the execution stream
  **directly** to the agent pod (never proxied through `control-plane`).
- Each component is detailed in
  [Components](/help/en/architecture/components).

## The path of a request

An agent turn follows the **managed path** (the only one authorized for the
production frontend). Three participants: the browser, `control-plane-backend`,
and a `fred-runtime` pod.

```mermaid
sequenceDiagram
  participant B as Browser
  participant CP as control-plane
  participant Pod as agent pod (fred-runtime)
  B->>CP: POST prepare-execution (Bearer JWT)
  Note over CP: validates team membership,<br/>resolves runtime binding + context
  CP-->>B: ExecutionPreparation (execute_stream_url, team_id, context)
  Note over CP,B: ingress-relative URL — no grant, no expiry
  B->>Pod: POST execute_stream_url (Bearer JWT, runtime_context.team_id)
  Note over Pod: validates Keycloak JWT,<br/>authorizes per-request (ReBAC OpenFGA)
  Pod-->>B: SSE stream (status, deltas, tool calls, final)
```

Key point: `control-plane` resolves **where** the agent runs (via
`prepare-execution`) but **issues no capability** and never proxies the SSE
stream. The browser calls the pod directly with the **user's Keycloak JWT**; the
pod authenticates that token and **authorizes** each request itself. The full
model is in [Security & authorization](/help/en/architecture/security).

## Why this shape

Three principles drive the split:

- **Decoupling.** The conversation path stays responsive while ingestion,
  evaluation, and background work run durably through `Temporal`.
- **Policy-first governance.** Execution decisions (model, tool/MCP, prompt,
  agent, data scope) are resolved from **policies**, not hardcoded.
- **Extensibility.** Agents are built and deployed in their own repositories;
  `control-plane` discovers and routes to them, with no dependency on the
  monorepo. From the user's perspective, a `custom-agent-pod` is
  indistinguishable from the bundled ones.
