# Platform Runtime Map (API Apps and Temporal Apps)

This page is the canonical map of where features belong in Fred.

Use it before adding endpoints, workflows, or policies.

## 1) API Applications

Fred has four API surfaces (one is being migrated out of the runtime path — see migration note below):

1. **Fred Runtime** (`fred-runtime`) — **target execution surface**
   - Main role: agent execution, SSE streaming, HITL pause/resume, checkpoints, runtime history.
   - All execution is team-scoped and authorized via `ExecutionGrant` from control-plane.
   - Exposes: `POST /agents/execute`, `POST /agents/execute/stream`, `GET /agents/sessions/...`
   - Secondary surface: `POST /v1/chat/completions` (OpenAI compat, for external tools only).
   - Runtime pods validate authorization but do not own tenancy, permissions, or routing.
   - Runtime observability is part of the execution surface: logs, KPI, metrics, and trace payloads must retain `user_id`, `team_id`, `agent_instance_id`, `session_id`, and trace correlation fields, including when exported to Langfuse.
   - The runtime CLI (`fred-agent-chat`) is a first-class backend validation client and must remain able to exercise managed team-scoped execution without frontend dependencies.

2. **Knowledge Flow Backend API** (`knowledge-flow-backend`)
   - Main role: ingestion, documents, tags/libraries, retrieval-facing operations.
   - Typical concerns: content lifecycle, metadata, vectors, document pipelines.

3. **Control Plane API** (`control-plane-backend`)
   - Main role: teams/users operations, policy-driven lifecycle control, **and (target) all product/session/admin concerns**.
   - Current concerns: team membership changes, policy evaluation, purge orchestration.
   - Target concerns (Phases 3–5): agent template/instance management, session metadata, MCP servers, permissions, frontend config, feedback.
   - Control-plane is the **sole authority** for: agentic pod discovery, agent enrollment, managed agent instance lifecycle, and `ExecutionGrant` issuance.
   - Phase 3a rule: keep control-plane APIs metadata-oriented. Session history and execution stay in `fred-runtime`.
   - Control-plane must issue enough identity/context for runtime observability enrichment; runtime validates and emits it but does not invent tenancy semantics locally.

4. **Agentic Backend API** (`agentic-backend`) — **being migrated out**
   - Current role: chat/session runtime and agent orchestration (frontend-facing).
   - This component is being progressively replaced by `fred-runtime` (execution) and `control-plane-backend` (product/session/admin).
   - Do not add new features here. New execution behavior goes to `fred-runtime`; new product/admin behavior goes to `control-plane-backend`.
   - See [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md) and `BACKLOG.md` for the migration plan.

> **Migration rule:** Rule 3 below ("Chat/session runtime behavior → Agentic API") is superseded.
> New chat/execution behavior goes to `fred-runtime`.
> New product/session/admin behavior goes to `control-plane-backend`.
> For the first control-plane migration slice, follow [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md).

## 2) Temporal Applications (Workers)

Fred also has Temporal workers separated by concern:

1. **Knowledge Flow Temporal Worker**
   - Runs ingestion/processing workflows.
   - Focus: batch conversion, extraction, indexing pipelines.

2. **Agentic Temporal Worker**
   - Runs long-running/scheduled agentic workloads (to be progressively consolidated there).
   - Focus: durable agent executions outside synchronous API request lifecycle.

3. **Control Plane Temporal Worker**
   - Runs lifecycle/policy jobs.
   - Focus: policy-based purge/archive workflows (for example member-removal cleanup).

## 3) Placement Rules

When adding new behavior, decide with these rules:

1. **User/team/admin API?** Put it in **Control Plane API**.
2. **Document ingestion/indexing pipeline?** Put it in **Knowledge Flow** (API + Temporal if async/batch).
3. **Agent execution, SSE streaming, HITL, checkpoints?** Put it in **fred-runtime**. _(Rule supersedes the old "Agentic API" rule.)_
4. **Policy-driven scheduled lifecycle action?** Put it in **Control Plane Temporal**.
5. **Cross-backend shared primitive?** Put it in **fred-core** (only if truly shared, stable, and minimal).
6. **New runtime contract type (execution identity, authorization, events)?** Put it in **fred-sdk** (`libs/fred-sdk/fred_sdk/contracts/`).

## 4) Startup Model (Same Pattern Across Apps)

All Python backends follow the same startup convention:

- `ENV_FILE` for secrets/env variables.
- `CONFIG_FILE` for YAML configuration.

Standard commands:

- `make run` for API process.
- `make run-worker` for Temporal worker process.

See:

- [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./CONFIGURATION_AND_POLICY_CONVENTIONS.md)

## 5) Related Docs

- Repository contract: [`docs/DEVELOPER_CONTRACT.md`](./DEVELOPER_CONTRACT.md)
- Access model (team rights): [`docs/REBAC.md`](./REBAC.md)
- Contribution workflow: [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md)
- Runtime execution contract (Phase 1): [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md)
- Control-plane product contract (Phase 3a): [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
- Migration plan: [`BACKLOG.md`](../../BACKLOG.md)
