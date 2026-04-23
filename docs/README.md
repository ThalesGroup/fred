# Documentation Index

Entry point for all Fred platform documentation.
Start here, then follow the links to the relevant section.

---

## Where to start

| I want to… | Go to |
|---|---|
| Understand the system architecture | [`design/`](#design--architecture-contracts) |
| Set up a dev environment | [`platform/DEVELOPER_CONTRACT.md`](platform/DEVELOPER_CONTRACT.md) |
| Deploy Fred | [`platform/DEPLOYMENT_GUIDE.md`](platform/DEPLOYMENT_GUIDE.md) |
| Write an agent with the SDK | [`authoring/`](#authoring) |
| See what the team is working on now | [`WORKPLAN.md`](WORKPLAN.md) |
| Understand the migration backlog | [`backlog/`](#backlog) |
| Read a technical proposal | [`rfc/`](#rfc) |

---

## Folder Map

### `design/` — Architecture contracts

Frozen contracts between components. Read these before touching any API boundary,
execution path, or session/team concern.

> **Note**: this folder will be renamed `architecture/` in a future cleanup commit
> once all cross-references in `CLAUDE.md` and backlogs are updated.

| File | What it defines |
|---|---|
| [`RUNTIME-EXECUTION-CONTRACT.md`](design/RUNTIME-EXECUTION-CONTRACT.md) | SSE execution contract, event types, grant lifecycle — read before touching fred-runtime or the frontend SSE connector |
| [`CONTROL-PLANE-PRODUCT-CONTRACT.md`](design/CONTROL-PLANE-PRODUCT-CONTRACT.md) | Product/session/admin API boundary — read before touching control-plane-backend |
| [`SESSION-IDENTITY-CONTRACT.md`](design/SESSION-IDENTITY-CONTRACT.md) | `session_id` ownership rules, thread_id ban, history vs metadata split |
| [`ARCHITECTURAL-SECURITY-REPORT.md`](design/ARCHITECTURAL-SECURITY-REPORT.md) | Security posture, grant trust, correlation check, planned hardening |
| [`AGENT_DESIGN.md`](design/AGENT_DESIGN.md) | Agent graph and authoring design |
| [`DESIGN.md`](design/DESIGN.md) | General system design overview |
| [`FILESYSTEM.md`](design/FILESYSTEM.md) | File system layout conventions |
| [`TABULAR_DATA_STORE.md`](design/TABULAR_DATA_STORE.md) | Tabular data store design |
| [`history-persistence.md`](design/history-persistence.md) | History persistence model |
| [`token-refresh.md`](design/token-refresh.md) | Token refresh flow |

---

### `platform/` — Platform, developer guides, and configuration

Developer contracts, coding conventions, configuration reference, and deployment
guides. Read the developer contract first.

**Developer guides**

| File | Purpose |
|---|---|
| [`DEVELOPER_CONTRACT.md`](platform/DEVELOPER_CONTRACT.md) | **Start here** — build, test, PR conventions |
| [`PYTHON_CODING_GUIDELINES.md`](platform/PYTHON_CODING_GUIDELINES.md) | Python style and quality rules |
| [`CONFIGURATION_AND_POLICY_CONVENTIONS.md`](platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md) | Config file conventions and policy rules |
| [`PLATFORM_RUNTIME_MAP.md`](platform/PLATFORM_RUNTIME_MAP.md) | Canonical map of services and their responsibilities |
| [`REBAC.md`](platform/REBAC.md) | ReBAC access control model (OpenFGA) |
| [`SECURITY.md`](platform/SECURITY.md) | Security practices |
| [`V2_AGENT_CREATION.md`](platform/V2_AGENT_CREATION.md) | How to create a v2 agent |
| [`FEATURES.md`](platform/FEATURES.md) | Platform feature inventory |

**Deployment and configuration**

| File | Purpose |
|---|---|
| [`DEPLOYMENT_GUIDE.md`](platform/DEPLOYMENT_GUIDE.md) | Main deployment guide |
| [`DEPLOYMENT_GUIDE_OPENSEARCH.md`](platform/DEPLOYMENT_GUIDE_OPENSEARCH.md) | OpenSearch-specific deployment |
| [`KEYCLOAK.md`](platform/KEYCLOAK.md) | Keycloak setup and configuration |
| [`ENV_VARIABLES.md`](platform/ENV_VARIABLES.md) | Environment variable reference |
| [`MODEL_CONFIGURATION.md`](platform/MODEL_CONFIGURATION.md) | LLM model configuration |
| [`LLM_ROUTING_FRED.md`](platform/LLM_ROUTING_FRED.md) | Fred LLM routing |
| [`LLM_ROUTING_PRIMER.md`](platform/LLM_ROUTING_PRIMER.md) | LLM routing concepts |
| [`TEMPORAL.md`](platform/TEMPORAL.md) | Temporal workflow setup |
| [`PROCESSING_GUIDE.md`](platform/PROCESSING_GUIDE.md) | Document processing pipeline |
| [`BENCHMARKS.md`](platform/BENCHMARKS.md) | Performance benchmarks |
| [`VERSIONING.md`](platform/VERSIONING.md) | Versioning policy |
| [`ROADMAP.md`](platform/ROADMAP.md) | Long-term product roadmap |

---

### `authoring/` — Agent SDK authoring

For engineers building agents with `fred-sdk`.

| File | Purpose |
|---|---|
| [`AGENTS.md`](authoring/AGENTS.md) | Agent authoring guide |
| [`SDK-V2-POSITIONING.md`](authoring/SDK-V2-POSITIONING.md) | SDK v2 philosophy and positioning |

---

### `backlog/` — Project state and sequencing

Current migration state, feature backlogs, and audit reports.
`BACKLOG.md` is the master sequencing document.

| File | Purpose |
|---|---|
| [`BACKLOG.md`](backlog/BACKLOG.md) | **Master backlog** — migration Phases 0→7, status and sequencing |
| [`FRONTEND-BACKLOG.md`](backlog/FRONTEND-BACKLOG.md) | Frontend Phase 5 adaptation plan |
| [`CHAT-UI-BACKLOG.md`](backlog/CHAT-UI-BACKLOG.md) | Chat UI quality build-out (Phases 6A→6D) |
| [`RUNTIME-FEATURE-AUDIT.md`](backlog/RUNTIME-FEATURE-AUDIT.md) | Current runtime feature inventory against target architecture |

---

### `rfc/` — Technical proposals

Architectural decision records and proposals. An RFC is a design proposal;
the resulting decisions get encoded in the `design/` contracts.

| File | Subject |
|---|---|
| [`AGENTIC-POD-RFC.md`](rfc/AGENTIC-POD-RFC.md) | Agentic pod architecture and migration direction |
| [`AGENT-EVALUATION-RFC.md`](rfc/AGENT-EVALUATION-RFC.md) | Agent evaluation framework (deepeval) |
| [`SDK-V2-RFC.md`](rfc/SDK-V2-RFC.md) | SDK v2 design proposal |
| [`DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md`](rfc/DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md) | Distributed agent architecture |

---

### `ops/` — Operations and maintenance

Runbooks and operational guides for the platform.

| File | Purpose |
|---|---|
| [`AGENT_POD_RUNTIME_PROTOCOL.md`](ops/AGENT_POD_RUNTIME_PROTOCOL.md) | Runtime pod protocol and operational contract |
| [`DATABASE_MIGRATIONS.md`](ops/DATABASE_MIGRATIONS.md) | Database migration runbook |

---

### Top-level operational documents

| File | Purpose |
|---|---|
| [`WORKPLAN.md`](WORKPLAN.md) | **Current sprint** — who does what, in what order, what is parallel |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution guidelines |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Code of conduct |

---

## Planned Cleanup

These structural changes are deferred until cross-references are updated in batch:

- `design/` → `architecture/` — the folder contains architecture contracts, not UI design; the rename is blocked on updating `CLAUDE.md` and all backlog cross-references in one commit
- `platform/` → split into `guides/` (developer guides) + `deployment/` (ops/config) — blocked on updating the many cross-references in `CLAUDE.md` mandatory read order
