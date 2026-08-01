---
title: Data stores
order: 30
description: PostgreSQL, OpenSearch, object storage, Temporal, OpenFGA, Keycloak — the role of each.
icon: database
---

# Data stores

Each store is specialized for one type of information. No application component
mixes these responsibilities.

| Store                   | Role                                                         |
| ----------------------- | ------------------------------------------------------------ |
| **`PostgreSQL`**        | State, sessions, conversation history, agent checkpoints     |
| **`OpenSearch`**        | Vector index for RAG retrieval                               |
| **Object storage (S3)** | Original documents and produced objects                      |
| **`Temporal`**          | Durable workflow orchestration (ingestion, background tasks) |
| **`OpenFGA`**           | ReBAC authorization engine (relationship tuples)             |
| **`Keycloak`**          | OIDC identity provider, JWT issuance                         |

## PostgreSQL

The relational state store: teams, agent instances, prompts, sessions and
**history**. It also holds the **checkpoints** that let `fred-runtime` restore an
agent's graph state between turns (the continuity key being `session_id`).

## OpenSearch

The **vector index** queried by `knowledge-flow` for RAG retrieval: the vector
representation of documents that lets an agent find the relevant passages and
rely on them.

## Object storage (S3-compatible)

The object store for **original documents** (uploaded or produced by agents).
The implementation is S3-compatible: `MinIO` in the reference configuration,
`SeaweedFS` locally, or cloud storage (`GCS`) depending on the deployment.

## Temporal

The **durable workflow** orchestrator. It carries document ingestion and
lifecycle tasks, run in the background without blocking the conversation path —
the pillar of the **decoupling** (see [Overview](/help/en/architecture/index)).

## OpenFGA & Keycloak

- **`OpenFGA`** — the **ReBAC** engine: it stores relationship tuples and answers
  the authorization checks (`CAN_USE_TEAM_AGENTS`…) run pod-side.
- **`Keycloak`** — the **OIDC** identity provider: user authentication and
  issuance of the **JWT** presented on every call.

How these two participate in authorization is detailed in
[Security & authorization](/help/en/architecture/security).

> The separation between object storage, vector index and metadata is what makes
> the **corpus audit** operation possible — it checks their consistency (see
> [Admin console](/help/en/features/admin)).
