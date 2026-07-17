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
| **A product manager** tracking progress                    | [`STATUS.md`](STATUS.md) → GitHub Issues/Milestones (`swift-golive`, `swift ga`)                                   |
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
| See what the team is working on now                   | [`STATUS.md`](STATUS.md) → GitHub Milestones (`swift-golive`, `swift ga`) |
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

### `data/` — Machine-readable sprint state

Structured data layer for fast AI and tool queries. **Always update these files
at the same time as the corresponding prose document** (STATUS.md or a backlog
checkbox). Both layers must stay in sync.

| File                                         | Purpose                                                                                   | Update trigger                                                     |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [`data/id-legend.yaml`](data/id-legend.yaml) | **Canonical ID registry** — every task ID, owner, status, domain, backlog cross-reference | When a new ID is created, a status changes, or a sub-item is added |
| [`data/sprint.yaml`](data/sprint.yaml)       | **Live sprint state** — milestones with % done, in-progress, next-up, blockers, velocity  | At the start and end of each session; when a task moves state      |

The IDs defined in `id-legend.yaml` are the same IDs used in commit messages,
backlog checkboxes, and STATUS.md. Canonical ID convention: see
[`../../CLAUDE.md §Task ID Convention`](../../CLAUDE.md).

---

### `backlog/` — Project state and sequencing

Feature backlogs and audit reports. `BACKLOG.md` itself (the runtime migration
backlog) is frozen — active work is tracked via GitHub Issues/Milestones, see
[`STATUS.md`](STATUS.md).

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
| [`AGENTIC-POD-RFC.md`](rfc/AGENTIC-POD-RFC.md)                                       | Agentic pod architecture and migration direction                                                                                                                                                        |
| [`DISCOVERED-RUNTIME-ROUTING-RFC.md`](rfc/DISCOVERED-RUNTIME-ROUTING-RFC.md)         | Config-driven frontend routing for discovered runtimes                                                                                                                                                  |
| [`AGENT-EVALUATION-RFC.md`](rfc/AGENT-EVALUATION-RFC.md)                             | Agent evaluation framework (deepeval) — EVAL-01 track                                                                                                                                                   |
| [`CHAT-RENDERING-SPEC.md`](rfc/CHAT-RENDERING-SPEC.md)                               | Chat message rendering specification — SSE, tool calls, attachments                                                                                                                                     |
| [`CHAT-UI-REFONTE-RFC.md`](rfc/CHAT-UI-REFONTE-RFC.md)                               | Chat UI refonte — ManagedChatPage, session lifecycle, option panel                                                                                                                                      |
| [`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`](rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md) | Active RUNTIME-07 hardening: signed execution grants, runtime authorization re-check, C3 readiness                                                                                                      |
| [`FRED-CHART-MODERNIZATION-RFC.md`](rfc/FRED-CHART-MODERNIZATION-RFC.md)             | Monorepo Helm chart migration to the modern `fred-agents` runtime topology                                                                                                                              |
| [`MCP-CATALOG-CONFIG-FIELDS-RFC.md`](rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md)           | MCP catalog config fields + tool-declared behavioral contracts (CTRLP-08)                                                                                                                               |
| `AGENT-INSTANCE-FORM-RFC.md` _(RFC pending — not yet written)_                       | Agent instance management form — template browser, tuning fields, MCP tools                                                                                                                             |
| [`MULTI-AGENT-MEMORY-HARDENING-RFC.md`](rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md)     | Multi-agent memory hardening: checkpoint isolation, remote/local execution convergence, TeamAgent history cap                                                                                           |
| [`PROMPT-SYSTEM-HARDENING-RFC.md`](rfc/PROMPT-SYSTEM-HARDENING-RFC.md)               | Prompt-system completion and hardening: agent-form prompt UX, scoped resolution, promotion metadata, marketplace, token KPIs                                                     |
| [`SDK-V2-RFC.md`](rfc/SDK-V2-RFC.md)                                                 | SDK v2 design proposal                                                                                                                                                                                  |
| [`DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md`](rfc/DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md) | Distributed agent architecture                                                                                                                                                                          |

---

### `ops/` — Operations and maintenance

Runbooks and operational guides for the platform.

| File                                                                 | Purpose                                       |
| -------------------------------------------------------------------- | --------------------------------------------- |
| [`AGENT_POD_RUNTIME_PROTOCOL.md`](ops/AGENT_POD_RUNTIME_PROTOCOL.md) | Runtime pod protocol and operational contract |
| [`DATABASE_MIGRATIONS.md`](ops/DATABASE_MIGRATIONS.md)               | Database migration runbook                    |
| [`KEA_SWIFT_CUTOVER.md`](ops/KEA_SWIFT_CUTOVER.md)                   | Kea to Swift cutover order, topic boundaries, and implementation state |
| [`KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`](ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md) | Keycloak identity bootstrap prerequisite for the cutover |

---

### Top-level operational documents

| File                                       | Purpose                                                                                                     |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| [`STATUS.md`](STATUS.md)                   | **Thin status pointer** — who's around, current focus, links to GitHub Milestones. Start here for quick status. |
| [`WORKPLAN.md`](WORKPLAN.md)               | Frozen 2026-07-16 — superseded by GitHub Milestones (`swift-golive`, `swift ga`)                            |
| [`TESTING.md`](TESTING.md)                 | **Release-candidate check** — four steps (offline tests → backing services → apps → auth validation suite), each with a pass/fail signal; linked from the repo root `README.md` |
| [`CONTRIBUTING.md`](CONTRIBUTING.md)       | Contribution guidelines                                                                                     |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Code of conduct                                                                                             |

---

## Planned Cleanup

These structural changes are deferred until cross-references are updated in batch:

- `design/` → `architecture/` — the folder contains architecture contracts, not UI design; the rename is blocked on updating `CLAUDE.md` and all backlog cross-references in one commit
- `platform/` → split into `guides/` (developer guides) + `deployment/` (ops/config) — blocked on updating the many cross-references in `CLAUDE.md` mandatory read order
