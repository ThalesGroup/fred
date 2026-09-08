## Why

Fred now ships a Deep Assistant and truthful ReAct tool-error reporting, but the Deep runtime still
deliberately disables filesystem use because its only available route is the legacy `/fs` surface.
The team needs one narrow, observable proof that a Deep Agent can plan a realistic multi-document
job, retain working state, and return only files that were truly persisted for the user.

The public synthetic `public-tender-response` knowledge base and
`reliable-tender-work-completion` use case in `fred-corpus` provide the fixed input and evaluator.
This change is tracked by #2328 (Deep integration and the tender proof) and #2498 (the scoped
Workspace vertical slice). #2498's complete, tested Workspace service is delivered as the first
ordered implementation phase of this same branch — not by a separate future PR — and Deep Workspace
writes stay disabled until that phase's security and binding requirements are fully implemented and
tested. The later phases then connect the Deep Agent to it.

## What Changes

- A scoped Knowledge Flow WorkspaceService (`list`/`read`/`write`/`link`) and its Control Plane
  binding-validation endpoint are implemented per `AGENT-FILESYSTEM-HARDENING-RFC.md` §9, with exact
  configured-client M2M identity, a server-derived namespace and fail-closed validation — the
  prerequisite this proof previously treated as external is now built as this change's first phase.
- Deep Agents use their existing `StateBackend` for ephemeral scratch and a new thin
  `FredWorkspaceBackend` route for durable `/workspace/` files through `WorkspaceFsPort`.
- The existing `artifacts.publish_text` built-in publishes the three final text artifacts and emits
  the canonical `PublishedArtifact`/`LinkPart`; no new artifact or download contract is introduced.
- The Deep Assistant's static “no filesystem” wording and legacy filesystem-MCP gate are replaced
  by runtime truth: tools are exposed only when their actual backend is available.
- One recorded integration run uses the exact public prompt and rubric, proving plan completion,
  document grounding, durable file verification, truthful failure handling and a final human
  decision request.

## Capabilities

### New Capabilities

- `deep-agent-tender-workspace-proof`: proves one Deep Agent can complete the versioned tender
  scenario with private working state and real user-visible Workspace artifacts.

### Modified Capabilities

None.

## Impact

- Knowledge Flow: new `workspace/` feature (`list`/`read`/`write`/`link`) and M2M client wiring.
- Control Plane: new internal binding-validation endpoint and an extracted, shared usability
  predicate (reused by `prepare_execution`).
- Runtime: `FredWorkspaceFs` migrated onto the M2M client identity; Deep backend construction and the
  `create_deep_agent` call in `fred-runtime`.
- Agent template: Deep Assistant filesystem wording and optional text-publication tool declaration.
- Tests: binding-validation isolation/actor-permission tests, backend mapping/bounds, runtime wiring,
  artifact truth and one scenario run record.
- Generated clients: `make update-knowledge-flow-api` and `make update-control-plane-api`.
- External fixture: the exact `fred-corpus` scenario revision is recorded, never copied into Fred.
- Tracking: #2328 (Deep integration and proof) and #2498 (Workspace vertical slice) stay separate
  GitHub issues; both are delivered as ordered, separately committed phases of this one branch, by
  default in one final PR — split into two PRs only if review scope requires it.

## Non-goals

- Restoring the legacy filesystem MCP server, or adding a second Workspace.
- ReAct parity, sub-agent orchestration, Graphify, Knowledge Base pull ingestion, or chat-side file
  browser work.
- Binary XLSX/DOCX generation, a new planner/TODO domain, a workflow engine, or general evaluator
  infrastructure.
- Exposing chain-of-thought or treating private reasoning as the oracle.
