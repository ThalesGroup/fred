# Platform Runtime Map (API Apps and Temporal Apps)

This page is the canonical map of where features belong in Fred.

Use it before adding endpoints, workflows, or policies.

## 1) API Applications

Fred has three API applications:

1. **Agentic Backend API** (`agentic-backend`)
   - Main role: chat/session runtime and agent orchestration.
   - Typical concerns: sessions, agent execution, chat interactions.

2. **Knowledge Flow Backend API** (`knowledge-flow-backend`)
   - Main role: ingestion, documents, tags/libraries, retrieval-facing operations.
   - Typical concerns: content lifecycle, metadata, vectors, document pipelines.

3. **Control Plane API** (`control-plane-backend`)
   - Main role: teams/users operations and policy-driven lifecycle control.
   - Typical concerns: team membership changes, policy evaluation, purge orchestration.

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
3. **Chat/session runtime behavior?** Put it in **Agentic API**.
4. **Policy-driven scheduled lifecycle action?** Put it in **Control Plane Temporal**.
5. **Cross-backend shared primitive?** Put it in **fred-core** (only if truly shared, stable, and minimal).

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
