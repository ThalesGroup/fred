# Documentation Index

Entry point for all Fred platform documentation.
Start here, then follow the links to the relevant section.

---

## Who are you?

| I am…                                                      | Start here                                                                                                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **A developer** setting up the environment                 | [`platform/DEVELOPER_CONTRACT.md`](platform/DEVELOPER_CONTRACT.md)                                                 |
| **A developer** validating or debugging a running service  | [`platform/CLI-CONVENTION.md`](platform/CLI-CONVENTION.md) — `make cli` on any pod                                 |
| **A developer** touching an API boundary or execution path | [`design/`](#design--architecture-contracts)                                                                       |
| **A developer** working on the chat UI                     | [`backlog/CHAT-UI-BACKLOG.md`](backlog/CHAT-UI-BACKLOG.md) then [`ux/COMPONENT-UX.md`](ux/COMPONENT-UX.md)         |
| **A UX designer** reviewing component rendering            | [`ux/COMPONENT-UX.md`](ux/COMPONENT-UX.md) then [`design/CHAT-COMPONENT-SPECS.md`](design/CHAT-COMPONENT-SPECS.md) |
| **A product manager** tracking progress                    | GitHub Issues/Milestones                                                                                            |
| **Anyone** validating a checkout or a release candidate    | [`TESTING.md`](TESTING.md) — four steps, each ending in a clear pass/fail answer                                   |
| **An architect** reviewing or proposing a change           | [`rfc/`](#rfc--technical-proposals) → [`design/`](#design--architecture-contracts)                                 |
| **Writing an agent** with the SDK                          | [`authoring/`](#authoring--agent-sdk)                                                                              |
| **Choosing how to run Fred** (standalone vs teams)         | [`platform/OPERATING_MODES.md`](platform/OPERATING_MODES.md)                                                       |
| **Deploying** the platform                                 | [`platform/DEPLOYMENT_GUIDE.md`](platform/DEPLOYMENT_GUIDE.md)                                                     |
| **An AI assistant** (Claude Code)                          | See [`../../CLAUDE.md`](../../CLAUDE.md) — mandatory read order defined there                                      |

---

## Document taxonomy

Four types of documents, each with a distinct purpose and lifecycle:

| Type                       | Folder     | Lifecycle                                                 | Who writes it  |
| -------------------------- | ---------- | --------------------------------------------------------- | -------------- |
| **Architecture contracts** | `design/`  | Stable — change only via RFC                              | Tech leads     |
| **Backlogs**               | `backlog/` | Append-only historical log — never delete past entries    | Dev team       |
| **UX state**               | `ux/`      | Living — updated each implementation cycle and UX session | Dev + Designer |
| **RFCs**                   | `rfc/`     | Proposal lifecycle — open → decided → archived            | Tech leads     |

**Cross-reference rule:** only this `README.md` points to everything. Other documents only
reference documents in the same folder or in `design/`. This prevents circular reference chains.

---

## Where to start

| I want to…                                            | Go to                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------ |
| Understand the system architecture                    | [`design/`](#design--architecture-contracts)                       |
| Set up a dev environment                              | [`platform/DEVELOPER_CONTRACT.md`](platform/DEVELOPER_CONTRACT.md) |
| Choose standalone vs full-stack mode                  | [`platform/OPERATING_MODES.md`](platform/OPERATING_MODES.md)       |
| Validate or debug a running service from the terminal | [`platform/CLI-CONVENTION.md`](platform/CLI-CONVENTION.md)         |
| Deploy Fred                                           | [`platform/DEPLOYMENT_GUIDE.md`](platform/DEPLOYMENT_GUIDE.md)     |
| Write an agent with the SDK                           | [`authoring/`](#authoring--agent-sdk)                              |
| See what the team is working on now                   | GitHub Issues/Milestones                                            |
| Understand the migration backlog                      | [`backlog/`](#backlog--project-state-and-sequencing)               |
| Check UX status of a chat component                   | [`ux/COMPONENT-UX.md`](ux/COMPONENT-UX.md)                         |
| Read a technical proposal                             | [`rfc/`](#rfc--technical-proposals)                                |

---

## Folder Map

### `design/` — Architecture contracts

Frozen contracts between components. Read these before touching any API boundary,
execution path, or session/team concern.

> **Note**: this folder will be renamed `architecture/` in a future cleanup commit
> once all cross-references in `CLAUDE.md` and backlogs are updated.

| File                                                                            | What it defines                                                                                                        |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| [`RUNTIME-EXECUTION-CONTRACT.md`](design/RUNTIME-EXECUTION-CONTRACT.md)         | SSE execution contract, event types, grant lifecycle — read before touching fred-runtime or the frontend SSE connector |
| [`CONTROL-PLANE-PRODUCT-CONTRACT.md`](design/CONTROL-PLANE-PRODUCT-CONTRACT.md) | Product/session/admin API boundary — read before touching control-plane-backend                                        |
| `SESSION-IDENTITY-CONTRACT.md` _(planned)_                                      | `session_id` ownership rules, thread_id ban, history vs metadata split                                                 |
| [`ARCHITECTURAL-SECURITY-REPORT.md`](design/ARCHITECTURAL-SECURITY-REPORT.md)   | Security posture, grant trust, correlation check, planned hardening                                                    |
| [`AGENT_DESIGN.md`](design/AGENT_DESIGN.md)                                     | Agent graph and authoring design                                                                                       |
| [`DESIGN.md`](design/DESIGN.md)                                                 | General system design overview                                                                                         |
| [`FILESYSTEM.md`](design/FILESYSTEM.md)                                         | File system layout conventions                                                                                         |
| [`MULTI_AGENT_MEMORY.md`](design/MULTI_AGENT_MEMORY.md)                         | Multi-agent conversational memory, checkpoint semantics, and invocation history propagation                              |
| [`PROMPTS.md`](design/PROMPTS.md)                                               | Prompt safety, prompt library, and multi-prompt chat context                                                           |
| `TABULAR_DATA_STORE.md` _(planned)_                                             | Tabular data store design                                                                                              |
| `history-persistence.md` _(planned)_                                            | History persistence model                                                                                              |
| `token-refresh.md` _(planned)_                                                  | Token refresh flow                                                                                                     |

---

### `platform/` — Platform, developer guides, and configuration

Developer contracts, coding conventions, configuration reference, and deployment
guides. Read the developer contract first.

**Developer guides**

| File                                                                                          | Purpose                                                                                          |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`DEVELOPER_CONTRACT.md`](platform/DEVELOPER_CONTRACT.md)                                     | **Start here** — build, test, PR conventions                                                     |
| [`BRANCH_STRATEGY.md`](platform/BRANCH_STRATEGY.md)                                           | **Branch model** — long-lived release branches, feature workflow, tagging, hotfix, future cycles |
| [`CLAUDE_CODE_ONBOARDING_FR.md`](platform/CLAUDE_CODE_ONBOARDING_FR.md)                       | **Onboarding** — branch strategy, Claude Code install, how to query the repo (FR)                |
| [`OPERATING_MODES.md`](platform/OPERATING_MODES.md)                                           | Standalone (single pod, no auth) vs full-stack (Keycloak + teams) — choose your mode             |
| [`CLI-CONVENTION.md`](platform/CLI-CONVENTION.md)                                             | **CLI pattern** — every backend exposes `make cli` / `fred-{component}-cli`                      |
| [`PYTHON_CODING_GUIDELINES.md`](platform/PYTHON_CODING_GUIDELINES.md)                         | Python style and quality rules                                                                   |
| [`FRONTEND_CODING_GUIDELINES.md`](platform/FRONTEND_CODING_GUIDELINES.md)                     | Frontend CSS/design-system rules — mandatory before touching `src/rework/`                       |
| [`CONFIGURATION_AND_POLICY_CONVENTIONS.md`](platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md) | Config file conventions and policy rules                                                         |
| [`PLATFORM_RUNTIME_MAP.md`](platform/PLATFORM_RUNTIME_MAP.md)                                 | Canonical map of services and their responsibilities                                             |
| [`QUALITY_REVIEW_PROTOCOL.md`](platform/QUALITY_REVIEW_PROTOCOL.md)                           | Evidence-based review modes for PR, release, architecture drift, and doc/governance audits       |
| [`REBAC.md`](platform/REBAC.md)                                                               | ReBAC access control model (OpenFGA)                                                             |
| [`OBSERVABILITY-AND-AUDIT.md`](platform/OBSERVABILITY-AND-AUDIT.md)                           | Observability, KPI & audit trail architecture — for architects and RSSI review                   |
| [`SECURITY.md`](platform/SECURITY.md)                                                         | Security practices                                                                               |
| [`V2_AGENT_CREATION.md`](platform/V2_AGENT_CREATION.md)                                       | How to create a v2 agent                                                                         |
| [`FEATURES.md`](platform/FEATURES.md)                                                         | Platform feature inventory                                                                       |

**Deployment and configuration**

| File                                                                        | Purpose                          |
| --------------------------------------------------------------------------- | -------------------------------- |
| [`DEPLOYMENT_GUIDE.md`](platform/DEPLOYMENT_GUIDE.md)                       | Main deployment guide            |
| [`DEPLOYMENT_GUIDE_OPENSEARCH.md`](platform/DEPLOYMENT_GUIDE_OPENSEARCH.md) | OpenSearch-specific deployment   |
| [`KEYCLOAK.md`](platform/KEYCLOAK.md)                                       | Keycloak setup and configuration |
| [`ENV_VARIABLES.md`](platform/ENV_VARIABLES.md)                             | Environment variable reference   |
| [`MODEL_CONFIGURATION.md`](platform/MODEL_CONFIGURATION.md)                 | LLM model configuration          |
| [`LLM_ROUTING_FRED.md`](platform/LLM_ROUTING_FRED.md)                       | Fred LLM routing                 |
| [`LLM_ROUTING_PRIMER.md`](platform/LLM_ROUTING_PRIMER.md)                   | LLM routing concepts             |
| [`TEMPORAL.md`](platform/TEMPORAL.md)                                       | Temporal workflow setup          |
| [`PROCESSING_GUIDE.md`](platform/PROCESSING_GUIDE.md)                       | Document processing pipeline     |
| [`BENCHMARKS.md`](platform/BENCHMARKS.md)                                   | Performance benchmarks           |
| [`VERSIONING.md`](platform/VERSIONING.md)                                   | Versioning policy                |

---

### `authoring/` — Agent SDK

For engineers building agents with `fred-sdk`.

| File                                                       | Purpose                           |
| ---------------------------------------------------------- | --------------------------------- |
| [`AGENTS.md`](authoring/AGENTS.md)                         | Agent authoring guide             |
| [`SDK-V2-POSITIONING.md`](authoring/SDK-V2-POSITIONING.md) | SDK v2 philosophy and positioning |

---

There is no machine-readable ID registry — `docs/swift/data/id-legend.yaml`
was removed (2026-07-27). The `DOMAIN-NN` shorthand can still appear
informally in commit messages and issue titles; convention: see
[`../../CLAUDE.md §Task ID convention`](../../CLAUDE.md).

Sprint state, issues, and milestones are **not** tracked in this repo's docs.
`STATUS.md`, `PMO-BOARD.md`, `data/sprint.yaml`, and `docs/PMO.md` were removed
because they duplicated GitHub without remaining current. GitHub
Issues/Milestones are the single source of truth; query them directly for
current status.

---

### `backlog/` — Project state and sequencing

Feature backlogs and audit reports. `BACKLOG.md` itself (the runtime migration
backlog) is frozen — active work is tracked via GitHub Issues/Milestones.

| File                                                                     | Purpose                                                                                  |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| [`BACKLOG.md`](backlog/BACKLOG.md)                                       | Frozen 2026-07-16 — migration Phases 0→7 history, ~90% done, superseded by GitHub        |
| [`FRONTEND-BACKLOG.md`](backlog/FRONTEND-BACKLOG.md)                     | Frontend Phase 5 adaptation plan                                                         |
| [`CHAT-UI-BACKLOG.md`](backlog/CHAT-UI-BACKLOG.md)                       | Chat UI quality build-out (Phases CHAT-01→CHAT-04)                                       |
| [`MULTI-AGENT-MEMORY-BACKLOG.md`](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | Cross-turn conversational memory for graph agents (design: `design/MULTI_AGENT_MEMORY.md`) |
| [`RUNTIME-FEATURE-AUDIT.md`](backlog/RUNTIME-FEATURE-AUDIT.md)           | Current runtime feature inventory against target architecture                            |

---

### `ux/` — UX review state

Per-component UX status for the chat interface: open issues, designer notes, and the agenda
for the next UX review session. Separate from implementation tasks (tracked in `backlog/`)
and from visual specs (defined in `design/CHAT-COMPONENT-SPECS.md`).

| File                                    | Purpose                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------- |
| [`COMPONENT-UX.md`](ux/COMPONENT-UX.md) | Status (Functional / Needs revision / Approved) + open issues per component |

---

### `rfc/` — Technical proposals

Architectural decision records and proposals. An RFC is a design proposal;
the resulting decisions get encoded in the `design/` contracts.

| File                                                                                 | Subject                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`AGENT-EVALUATION-RFC.md`](rfc/AGENT-EVALUATION-RFC.md)                             | Agent evaluation framework (deepeval) — EVAL-01 track                                                                                                                                                   |
| [`AGENT-FILESYSTEM-HARDENING-RFC.md`](rfc/AGENT-FILESYSTEM-HARDENING-RFC.md)         | Agent filesystem completion and hardening — remaining `FILES-04`/`FILES-05` gaps and the `RUNTIME-07` security dependency                                                                               |
| [`AGENTIC-POD-RFC.md`](rfc/AGENTIC-POD-RFC.md)                                       | Fred Runtime Discovery Contract (FRDC v1) — Kubernetes-native pod auto-discovery via Service labels/annotations; not yet implemented, static catalog is the production mechanism                        |
| [`CAPABILITY-EXECUTION-FLOW-RFC.md`](rfc/CAPABILITY-EXECUTION-FLOW-RFC.md)           | Vocabulary (Agent / Capability execution flow / Application Workflow) + a durable Temporal-backed tier for capability-internal orchestration (e.g. `document_extract`'s map phase) — open design question, extends TEMPORAL.md and #2240's pattern |
| [`DELEGATED-DOWNSTREAM-AUTH-RFC.md`](rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md)           | AUTH-TX — token exchange at admission so the pod stops forwarding a fixed-lifetime user bearer for an unbounded turn; follow-up to #2125, multi-repo (realm templates), design only                     |
| [`DOCUMENT-VIEWER-AI-PANEL-RFC.md`](rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md)             | "Ask the assistant" side panel next to the document viewer — blocked on an agent-picker product decision                                                                                                |
| [`FRED-TEAM-CONFIG-RFC.md`](rfc/FRED-TEAM-CONFIG-RFC.md)                             | Team configuration: ownership, objects, and authorization boundaries                                                                                                                                     |
| [`MULTI-AGENT-MEMORY-HARDENING-RFC.md`](rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md)     | Multi-agent memory hardening: checkpoint isolation, remote/local execution convergence, TeamAgent history cap, invocation depth/cycle limit                                                            |
| [`PROMPT-SYSTEM-HARDENING-RFC.md`](rfc/PROMPT-SYSTEM-HARDENING-RFC.md)               | Prompt-system completion and hardening: agent-form prompt UX, scoped resolution, promotion metadata, marketplace, token KPIs                                                     |
| [`SDK-V2-RFC.md`](rfc/SDK-V2-RFC.md)                                                 | SDK v2 design proposal                                                                                                                                                                                  |
| [`TASK-EVENT-STREAM-RFC.md`](rfc/TASK-EVENT-STREAM-RFC.md)                           | OPS-04 — unified task event stream, worker-action audit log, and the shared admin Activity surface                                                                                                      |
| [`TEAM-PLATFORM-POLICY-RFC.md`](rfc/TEAM-PLATFORM-POLICY-RFC.md)                     | Team platform policy — storage, ingestion, size, deletion retention, tool guardrails (model/MCP allowlisting is out of scope, governed by the capability system instead)                                |

---

### `ops/` — Operations and maintenance

Runbooks and operational guides for the platform.

| File                                                                 | Purpose                                       |
| -------------------------------------------------------------------- | --------------------------------------------- |
| [`AGENT_POD_RUNTIME_PROTOCOL.md`](ops/AGENT_POD_RUNTIME_PROTOCOL.md) | Runtime pod protocol and operational contract |
| [`DATABASE_MIGRATIONS.md`](ops/DATABASE_MIGRATIONS.md)               | Database migration runbook                    |
| [`KEA_SWIFT_CUTOVER.md`](ops/KEA_SWIFT_CUTOVER.md)                   | Kea to Swift cutover order, topic boundaries, and implementation state |

---

### Top-level operational documents

| File                                       | Purpose                                                                                                     |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| [`WORKPLAN.md`](WORKPLAN.md)               | Frozen 2026-07-16 — superseded by GitHub Milestones (`swift-golive`, `swift ga`)                            |
| [`TESTING.md`](TESTING.md)                 | **Release-candidate check** — four steps (offline tests → backing services → apps → auth validation suite), each with a pass/fail signal; linked from the repo root `README.md` |
| [`CONTRIBUTING.md`](CONTRIBUTING.md)       | Contribution guidelines                                                                                     |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Code of conduct                                                                                             |

---

## Planned Cleanup

These structural changes are deferred until cross-references are updated in batch:

- `design/` → `architecture/` — the folder contains architecture contracts, not UI design; the rename is blocked on updating `CLAUDE.md` and all backlog cross-references in one commit
- `platform/` → split into `guides/` (developer guides) + `deployment/` (ops/config) — blocked on updating the many cross-references in `CLAUDE.md` mandatory read order
