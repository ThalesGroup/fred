# docs/ARCHITECTURE.md

Entry point for architecture orientation. Each component is described in one sentence.
For topology detail, see `docs/swift/platform/`. For frozen contracts, see
`docs/swift/design/`.

---

## Active components

| Component | Role |
|---|---|
| `libs/fred-sdk` | Shared execution contracts, SDK types, and prompt utilities |
| `libs/fred-runtime` | Execution framework library — agent engine, SSE, HITL, checkpoints |
| `libs/fred-core` | Cross-cutting utilities — caching, config, logging, KPI stores |
| `apps/fred-agents` | Production agent pod — runnable agent definitions built on `fred-runtime` |
| `apps/control-plane-backend` | Product/session/admin APIs and ExecutionGrant issuance |
| `apps/knowledge-flow-backend` | Document ingestion, retrieval, and knowledge management |
| `frontend/` | React SPA — chat UI, agent management, session lifecycle |

`ignored/fred/agentic-backend` is **archived** — do not reference it as a target or
active service. The backend migration from `agentic-backend` is complete.

---

## Where to read more

| Topic | Document |
|---|---|
| Full topology and service boundaries | `docs/swift/platform/PLATFORM_RUNTIME_MAP.md` |
| Execution contract (frozen) | `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` |
| Product/session/admin contract (frozen) | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| ReBAC access model | `docs/swift/platform/REBAC.md` |
| Configuration and policy conventions | `docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md` |
| Frontend rework coding rules | `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` |
| Developer contract overview | `docs/swift/platform/DEVELOPER_CONTRACT.md` |

---

## Current migration state (2026-05-11)

The backend migration from `agentic-backend` is complete. One frontend cleanup
remains: Phase FRONT-05 removes ~30 residual imports from `agenticOpenApi.ts`.
Tracked in `docs/swift/backlog/FRONTEND-BACKLOG.md §7`.
