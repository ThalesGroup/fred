# Platform Runtime Map (API Apps and Temporal Apps)

This page is the canonical map of where features belong in Fred.

Use it before adding endpoints, workflows, or policies.

## 1) API Applications

Fred has three active API surfaces:

1. **Fred Agents pod** (`apps/fred-agents`) — **production agent execution surface**
   - Main role: hosts runnable agent definitions built on `fred-runtime` and `fred-sdk`.
   - Exposes: `POST /agents/execute`, `POST /agents/execute/stream`, `GET /agents/sessions/...`
   - Secondary surface: `POST /v1/chat/completions` (OpenAI compat, for external tools only).
   - All execution is team-scoped and authorized via `ExecutionGrant` from control-plane.
   - Runtime observability is part of the execution surface: logs, KPI, metrics, and trace payloads must retain `user_id`, `team_id`, `agent_instance_id`, `session_id`, and trace correlation fields, including when exported to Langfuse.
   - The execution framework itself lives in `libs/fred-runtime`; the agent definitions live here.
   - Exposes `make cli` / `fred-agents-cli` as its first-class backend validation client. See [CLI-CONVENTION.md](CLI-CONVENTION.md).

2. **Knowledge Flow Backend API** (`knowledge-flow-backend`)
   - Main role: ingestion, documents, tags/libraries, retrieval-facing operations.
   - Typical concerns: content lifecycle, metadata, vectors, document pipelines.

3. **Control Plane API** (`control-plane-backend`)
   - Main role: teams/users operations, policy-driven lifecycle control, and all product/session/admin concerns.
   - Concerns: team membership, policy evaluation, purge orchestration, agent template/instance management, session metadata, MCP servers, permissions, frontend config, feedback.
   - Control-plane is the **sole authority** for: agentic pod discovery, agent enrollment, managed agent instance lifecycle, and `ExecutionGrant` issuance.
   - Keep control-plane APIs metadata-oriented. Session history and execution stay in `apps/fred-agents`.
   - Control-plane must issue enough identity/context for runtime observability enrichment; runtime validates and emits it but does not invent tenancy semantics locally.

> **`agentic-backend` is removed.** It was the former chat/session runtime and agent orchestration
> surface. It has been archived to `ignored/fred/agentic-backend` and is no longer active.
> The backend migration is complete. What remains is Phase FRONT-05: removing the ~30 frontend files that
> still import types from `agenticOpenApi.ts` (generated from the removed service's schema).
> See [`docs/swift/backlog/FRONTEND-BACKLOG.md §7`](../backlog/FRONTEND-BACKLOG.md).

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
3. **Agent execution, SSE streaming, HITL, checkpoints?** New agent definitions go in `apps/fred-agents`; execution framework changes go in `libs/fred-runtime`.
4. **Policy-driven scheduled lifecycle action?** Put it in **Control Plane Temporal**.
5. **Cross-backend shared primitive?** Put it in **fred-core** (only if truly shared, stable, and minimal).
6. **New runtime contract type (execution identity, authorization, events)?** Put it in **fred-sdk** (`libs/fred-sdk/fred_sdk/contracts/`).

## 4) CLI Convention (Same Pattern Across Apps)

**Every Fred backend service exposes `make cli`.**

This is a platform design decision: the CLI is not a convenience, it is the primary
backend validation and operations tool for each service. Use it to validate execution
contracts, auth flows, session continuity, KPIs, and managed execution — without a
browser or a running frontend.

| Component | Executable | Status |
|---|---|---|
| `fred-agents` (agent execution) | `fred-agents-cli` | ✅ live |
| `knowledge-flow-backend` | `fred-kf-cli` | planned |
| `control-plane-backend` | `fred-cp-cli` | planned |

Full specification: [`CLI-CONVENTION.md`](CLI-CONVENTION.md).

## 5) Future: Kubernetes-Native Runtime Discovery (FRDC v1 — Proposed)

The current `runtime_catalog_sources` config is a static list maintained manually. A proposed follow-up — the **Fred Runtime Discovery Contract (FRDC v1)** — defines a Kubernetes-native auto-discovery mechanism using Service labels (`fred.io/runtime=true`) and annotations. When implemented, this would replace the static catalog with a reconciler loop that watches the Kubernetes API for labeled Services.

**Current status:** Proposed. Not yet implemented. The static catalog in `§5.1` is the authoritative production mechanism. See [`docs/swift/rfc/AGENTIC-POD-RFC.md`](../rfc/AGENTIC-POD-RFC.md) for the full spec.

---

## 5) Startup Model (Same Pattern Across Apps)

All Python backends follow the same startup convention:

- `ENV_FILE` for secrets/env variables.
- `CONFIG_FILE` for YAML configuration.

Standard commands:

- `make run` for API process.
- `make run-worker` for Temporal worker process.

See:

- [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./CONFIGURATION_AND_POLICY_CONVENTIONS.md)

## 5.1 Runtime Catalog Sources

When the frontend uses managed agents, `control-plane-backend` needs a static
list of reachable runtime pods in:

- `platform.runtime_catalog_sources`

This is the only deployment-time runtime catalog config that belongs in the
control-plane product surface.

Each entry has exactly three important fields:

- `runtime_id`
  - stable logical identifier for one runtime pod family
  - stored on managed agent instances after enrollment
- `base_url`
  - server-side URL used by `control-plane-backend`
  - must be reachable from the control-plane process
  - must already include the runtime pod base path
  - template discovery happens at `{base_url}/agents/templates`
- `ingress_prefix`
  - browser-facing relative URL prefix returned by `prepare-execution`
  - must match the path exposed by your ingress, reverse proxy, or local Vite
    proxy
  - must already include the runtime pod base path

Example:

```yaml
platform:
  runtime_catalog_sources:
    - runtime_id: fred-samples-agents
      base_url: http://127.0.0.1:8010/samples/agents/v1
      enabled: true
      ingress_prefix: /samples/agents/v1
    - runtime_id: fred-agents
      base_url: http://127.0.0.1:8000/fred/agents/v2
      enabled: true
      ingress_prefix: /fred/agents/v2
```

Important rules:

- `base_url` is for control-plane only; the frontend never uses it directly.
- `ingress_prefix` is for the frontend only; it becomes:
  - `{prefix}/agents/execute`
  - `{prefix}/agents/execute/stream`
  - `{prefix}/agents/sessions/{session_id}/messages`
- `base_url` and `ingress_prefix` normally share the same base path suffix, but
  may differ in host because one is server-side and the other is browser-side.
- `ingress_prefix` must stay ingress-relative and must not expose
  `*.svc.cluster.local`, pod IPs, or other cluster-internal topology.

Local development checklist:

1. Start the runtime pod on its local port.
2. Copy the runtime pod `app.base_url` exactly into `runtime_catalog_sources.*.base_url`.
3. Expose the same base path to the browser with Vite or your reverse proxy.
4. Use that exposed browser path as `runtime_catalog_sources.*.ingress_prefix`.

For local Vite development this usually means:

- `base_url: http://127.0.0.1:<port>/<runtime-base-path>`
- `ingress_prefix: /<runtime-base-path>`

If templates are visible in `GET /teams/{team_id}/agent-templates` but managed
chat fails, the usual cause is a correct `base_url` with a wrong
`ingress_prefix` or missing frontend proxy rule.

## 4.2 Managed Agent Lifecycle And Availability

This is the canonical naming and lifecycle model for managed agents.

Use these terms consistently in code, docs, UI labels, and backlog items.

### Terms

1. `AgentTemplate`
   - a capability discovered live from one configured runtime pod
   - public identity: `template_id = {runtime_id}:{source_agent_id}`
   - used only for enrollment

2. `ManagedAgentInstance`
   - a team-scoped product object created by enrolling one template
   - stored in the `control-plane-backend` database
   - public execution identity: `agent_instance_id`

3. `RuntimeBinding`
   - the internal control-plane mapping from one managed instance to the
     runtime source and runtime agent id it executes against
   - not a separate user-facing product object

### Lifecycle

1. `control-plane-backend` discovers templates live from
   `platform.runtime_catalog_sources[*]`.
2. A team enrolls one discovered template.
3. `control-plane-backend` creates one DB-backed `ManagedAgentInstance`.
4. Later execution uses `agent_instance_id`, never `source_agent_id`.
5. `prepare-execution` resolves the internal runtime binding and returns
   ingress-safe runtime URLs.
6. Unbinding deletes only the managed instance record from control-plane.

### Availability Model

Managed agents have two different availability dimensions. Keep them separate.

1. Catalog availability
   - asks: "is the template currently discoverable from a live runtime pod?"
   - source of truth: `GET /teams/{team_id}/agent-templates`
   - if the runtime pod is down, its templates disappear from discovery

2. Instance availability
   - asks: "does the team still own this enrolled managed agent instance?"
   - source of truth: `GET /teams/{team_id}/agent-instances`
   - enrollment persists in the DB even if the runtime pod is currently down

### Required Behavior When A Runtime Pod Is Down

If a runtime pod becomes unavailable after enrollment:

1. template discovery from that pod may fail, so new enrollment from that pod is
   unavailable
2. already enrolled `ManagedAgentInstance` records remain visible in the
   control-plane listing
3. managed execution may fail at preparation time or at the subsequent runtime
   call, depending on what exactly is unavailable
4. unbinding must still work because it is a control-plane DB operation, not a
   runtime call

### Current Implementation Note

Today the implementation behaves as follows:

1. if a configured runtime source cannot be reached for template discovery, its
   templates are omitted from the aggregated catalog
2. an enrolled `ManagedAgentInstance` remains listed because it is DB-backed
3. if the runtime source is removed or disabled in control-plane config,
   `prepare-execution` fails with `503`
4. if the runtime source remains configured but the runtime pod is down,
   `prepare-execution` may still succeed and the later browser-to-runtime call
   fails
5. unbinding continues to work because delete is handled entirely by
   `control-plane-backend`

### Frontend Rule

The frontend must not collapse discovery state and enrollment state into a
single "agent exists / agent missing" concept.

For one enrolled managed instance, the UI should be able to communicate:

- the instance still exists for the team
- the backing runtime is currently unavailable for new execution
- delete / unbind is still allowed when the user has that permission

This distinction is required for a simple and robust operator experience.

## 6) Related Docs

- Repository contract: [`docs/DEVELOPER_CONTRACT.md`](./DEVELOPER_CONTRACT.md)
- Access model (team rights): [`docs/REBAC.md`](./REBAC.md)
- Contribution workflow: [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md)
- Runtime execution contract (Phase 1): [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md)
- Control-plane product contract (Phase 3a): [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
- Migration plan: [`BACKLOG.md`](../../BACKLOG.md)
