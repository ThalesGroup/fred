## Context

`DeepAgentRuntime` already delegates planning to `deepagents.create_deep_agent` while retaining
Fred's ReAct transport, events, observability and checkpointer. `deepagents==0.6.12` accepts a
`BackendProtocol` and supplies native TODO and filesystem middleware. Fred currently does not pass a
backend; instead it looks for legacy filesystem MCP tools and blocks the native filesystem tool
names when none are bound.

The accepted Workspace target is already recorded in
`AGENT-FILESYSTEM-HARDENING-RFC.md` §9: `CompositeBackend(default=StateBackend(),
routes={"/workspace/": FredWorkspaceBackend(...)})`. The remote API remains the four operations
owned by #2498: list, read, write and link. The model never constructs a physical storage prefix.
This change's Phase 2 implements that vertical slice directly — the Knowledge Flow `workspace/`
service, its Control Plane binding-validation endpoint, and `FredWorkspaceFs`'s migration onto the
runtime's own M2M identity — rather than treating #2498 as work delivered elsewhere. Phase 3 then
wires the Deep-side `FredWorkspaceBackend` adapter against it.

The first outcome fixture lives in the sibling public repository:

- knowledge base: `corpora/public-tender-response/source/`;
- canonical prompt and rubric: `use-cases/reliable-tender-work-completion/`;
- excluded from ingestion: every `validation/` file.

## Goals / Non-Goals

**Goals**

- Prove the existing Deep Agent planner can finish one fixed multi-step request.
- Give Deep native scratch plus a durable, server-scoped `/workspace/` route.
- Make successful publication, not prose, the truth boundary for user files.
- Produce a small baseline and one witnessed acceptance result that other agent/prompt work can
  compare against unchanged.

**Non-goals**

- A statistical production-reliability claim; repeatability hardening follows the first proof.
- A new file, link, plan, HITL or evaluation API.
- Office-binary creation. The first proof uses UTF-8 CSV and Markdown only.
- Replacing the Deep Agent library's TODO middleware or persisting private chain-of-thought.

## Decisions

### D1 — One vertical outcome, one fixed fixture

The first success is a Deep-only integration proof using the exact committed `fred-corpus` prompt.
Its revision, Fred revision, model profile, agent/template version, enabled capabilities, elapsed
time, tool/model calls and token usage are recorded. The current ReAct path is not a gate for this
slice; it can later run the same fixture without changing its contract.

### D2 — Existing owners remain canonical

The Knowledge Base is read through the existing `document_access` capability. Deep planning and
TODO state remain owned by Deep Agents and Fred's existing checkpointer. Mutable durable files are
owned by WorkspaceService/`WorkspaceFsPort`. User-visible files remain
`PublishedArtifact` → `LinkPart` runtime/UI parts. No layer mirrors any of these concepts.

### D3 — Phase 2 builds #2498's Workspace vertical slice directly

This change's second phase implements the RFC §9.10 vertical slice as one functional unit, not
independently-mergeable fragments, and lands as its own commit/PR boundary before any Deep-side code
touches it:

- the internal Control Plane binding-validation endpoint (§9.5), reusing — not reimplementing — the
  `enabled`/not-`suspended` usability predicate `prepare_execution` already applies;
- Knowledge Flow's `workspace/` feature exposing exactly `list`, `read`, `write`, `link` (§9.2); no
  `delete`, `edit`, `glob`, `grep`, `mkdir`, or other operation is added to the remote contract
  (§9.3);
- exact configured-client M2M identity enforcement at both boundaries — the verified JWT `azp`/
  client-ID claim, never `service_agent` alone, `preferred_username`, or an unverified header (§9.5);
- `FredWorkspaceFs` migrated off the human/runtime bearer token and off caller-constructed physical
  paths, onto the runtime's own M2M client-credentials identity and a server-derived namespace
  (§9.1, §9.1a);
- `LocalRegistryAgentInvoker` fixed to preserve the parent's `(team_id, agent_instance_id, user_id,
  session_id)` binding onto a delegated child's execution request, replacing today's
  `agent_instance_id=None` (§9.4);
- generated-contract regeneration for both touched backends (`make update-knowledge-flow-api`,
  `make update-control-plane-api`);
- isolation and actor-permission tests (§9.1a, §9.7): human read/list/link-only, agent
  read/write/list/link within its bound subtree only, cross-binding rejection, a human JWT rejected
  outright on the agent-write path;
- the `workspace.binding_validation_latency_ms` KPI on the existing bounded `status` label, using an
  application-scoped async `httpx.AsyncClient` with a bounded timeout that fails closed on timeout,
  connection error or a malformed response (§9.5).

Deep Workspace writes stay disabled — the composite backend route is not built — until every item
above is implemented and its tests pass. Phase 3 (D4 below) does not start until Phase 2 is merged
and verified; RFC §9.10 explicitly excludes the Deep Agents `CompositeBackend` integration from "the
first PR," so Phase 2 and Phase 3 stay separate commits even though both land on this one branch.

### D4 — CompositeBackend separates scratch from durable files

`DeepAgentRuntime` passes a backend to `create_deep_agent`:

```python
CompositeBackend(
    default=StateBackend(),
    routes={"/workspace/": FredWorkspaceBackend(workspace_fs)},
)
```

`StateBackend` owns ephemeral scratch and Deep's internal large-result storage. The Fred route owns
only `/workspace/`. The plan proof writes `/workspace/plan.md` so the next turn can re-read the
explicit checklist without exposing hidden reasoning. Every operation uses the already-bound
`WorkspaceFsPort`; the model supplies only a virtual path.

### D5 — The adapter is thin and asynchronous

`FredWorkspaceBackend` implements the Deep `BackendProtocol` async methods over the four-operation
Workspace contract. It translates Deep result types without introducing another storage client or
authentication path. Deep's `write` remains create-only as its protocol requires; the adapter
checks existence before the Workspace create/replace operation. `edit` composes read plus write.
`glob` and `grep` compose bounded list/read
operations with explicit file-count and per-file byte limits. The implementation must state and
test those limits. Command execution is unsupported and therefore absent from the model tool list,
as Deep's middleware already filters `execute` for a non-sandbox backend.

No sync method may bridge async I/O through a new event loop or blocking network call. All model-
reachable methods must terminate in a result, never `NotImplementedError`.

### D6 — Final publication reuses `artifacts.publish_text`

The proof's outputs are `compliance-matrix.csv`, `bid-recommendation.md`, and `response-plan.md`.
The Deep Assistant makes the existing `artifacts.publish_text` tool selectable for the scenario.
That tool writes through the same `WorkspaceFsPort` and returns a typed link part. The agent then
reads the corresponding `/workspace/` paths to verify non-empty, mutually consistent contents.

Internal scratch and `/workspace/plan.md` are not automatically linked. A filename in the final
answer without a successful typed publication is not a deliverable. An artifact tool failure must
remain an explicit partial failure and must not produce a synthetic Markdown URL.

### D7 — Filesystem availability is derived from the backend

The Deep Assistant no longer hard-codes that files are unavailable. `DeepAgentRuntime` no longer
uses the presence of legacy MCP filesystem tool names as its backend gate. When the scoped
Workspace port is available, it builds the composite backend. Until Phase 2 (D3) is complete and
tested, the durable route stays disabled rather than routing Deep to legacy `/fs`. The Deep
`StateBackend` may still support internal scratch, but neither the prompt nor the final answer may
describe it as durable or user-visible Workspace storage.

### D8 — HITL remains conversational in the first proof

The canonical prompt requires the agent to prepare and verify the dossier, then ask the user for a
go/no-go decision. This proves correct placement of the human decision without adding tool approval
or a new pause lifecycle. Durable HITL implementation remains owned by #1080.

### D9 — One witnessed run is a proof, not a reliability guarantee

The first milestone requires a rubric score of at least 80/100 and no hard failure. Unit and
integration tests lock storage, isolation, path and publication invariants. A later reliability
slice may reintroduce the closed #2568 target of repeated runs; this change does not claim that one
model execution establishes statistical reliability.

## Risks / Trade-offs

- Phase 2 (#2498's Workspace vertical slice, D3) is substantial security-sensitive work in its own
  right — a new Control Plane endpoint, exact-client M2M identity, and a `FredWorkspaceFs` credential
  migration — landing inside this same branch/change rather than as a separately-scheduled PR. Its
  scope must not be compressed to fit the Deep-proof timeline: Phase 3 does not start, and Deep
  Workspace writes stay fail-closed, until Phase 2's own tests and an independent `/code-review` pass
  are complete. Phase 2 and Phase 3 land as separate commits so Phase 2 stays independently
  reviewable and revertible without pulling Deep-side code with it.
- Text-only outputs prove the full file-truth loop but not Office generation. Adding XLSX/DOCX now
  would introduce a separate generator/capability problem and obscure the Workspace proof.
- Composed `glob` and `grep` require strict traversal limits. Overly small limits reduce utility;
  unbounded limits create latency and load risk. The implementation records measured choices.
- `artifacts.publish_text` and Deep filesystem writes share storage but serve different semantics:
  private working mutation versus explicit user publication. Their path mapping must be tested as
  one namespace, not assumed.

## Migration Plan

No data migration. Phase 2 (D3) implements #2498's Workspace contract and M2M binding validation as
part of this change; Phase 3's Deep backend route lands only after Phase 2's tests and review pass.
Rollback of Phase 3 removes the Deep backend route and optional publication declaration without
touching Phase 2. Phase 3 cannot exist without Phase 2, but Phase 2 has no dependency on Phase 3 and
may ship (and be rolled back) independently. Existing ReAct, Workspace and Deep-without-Workspace
behavior remains available throughout.

## Open Questions

- The concrete `glob`/`grep` file-count and byte limits must be selected from a focused local
  performance measurement during implementation, then documented in the compact runtime contract.
