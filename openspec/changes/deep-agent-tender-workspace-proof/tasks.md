This checklist delivers one Deep Agent + Workspace proof across two GitHub-tracked, separately
committed phases on one branch: #2498's scoped WorkspaceService (group 2) and #2328's Deep
integration and tender proof (groups 3-5). It does not reopen the completed ReAct error-correction
slice (#2568, already merged). Deep Workspace writes stay disabled and group 3 does not start until
every group-2 task is implemented, tested and independently reviewed.

## 0. Freeze the external fixture and tracking boundary

- [ ] 0.1 Commit the synthetic `public-tender-response` knowledge base and
      `reliable-tender-work-completion` prompt/rubric/run-record template in `fred-corpus`; validate
      JSON, provenance, sensitivity and ensure `validation/` is excluded from ingestion.
- [ ] 0.2 Record the resulting `fred-corpus` commit in the first baseline/acceptance report; do not
      copy the source documents or ground truth into Fred.
- [ ] 0.3 Confirm #2328 (Deep integration/proof) and #2498 (Workspace vertical slice) both stay open
      as separate GitHub tracking issues for this branch's two ordered, separately committed phases.
      If that tracking changes, update GitHub before implementation rather than creating a competing
      issue silently.

## 1. Record the current Deep baseline

- [ ] 1.1 Manually ingest only `corpora/public-tender-response/source/` into a test team's Knowledge
      Base and configure one Deep Assistant with document access.
- [ ] 1.2 Run the canonical prompt unchanged on the current baseline and preserve the transcript,
      trace, available tool list and any produced files.
- [ ] 1.3 Score the run with the committed rubric and classify each failure as retrieval,
      planning/instruction-following, missing backend/tool, publication, or UI/history transport.
      Do not change prompts or code during this diagnostic task.

## 2. Build the secure Workspace vertical slice (#2498)

- [ ] 2.1 Extract `prepare_execution`'s `enabled`/not-`suspended` usability predicate
      (`product/service.py`) into one function shared with the new binding validator, so the rule is
      never implemented twice.
- [ ] 2.2 Implement the internal Control Plane binding-validation endpoint: validate session
      existence, `session.user_id`/`session.team_id` match, agent-instance existence/team match, the
      session's recorded `agent_instance_id` when present, and the shared usability predicate.
      Require the exact configured Knowledge Flow M2M client identity via a verified JWT
      `azp`/client-ID claim — add it to the typed authentication principal or an equivalent verified-
      client dependency; `service_agent` role alone, `preferred_username`, or an unverified header
      must never satisfy this check.
- [ ] 2.3 Implement Knowledge Flow's `workspace/` feature exposing exactly `list`, `read`, `write`,
      `link`. Add no `delete`, `edit`, `glob`, `grep`, `mkdir`, `rename`, `stat`, or paginated
      operation to the remote contract. Require the exact configured runtime/agentic M2M client
      identity on every call; derive the physical namespace server-side from the verified binding,
      never from a caller-supplied path.
- [ ] 2.4 Migrate `FredWorkspaceFs` off `_workspace_access_token`/the human bearer path and onto the
      runtime's own M2M client-credentials identity (`M2MTokenProvider`). Call the binding-validation
      endpoint before every M2M Workspace operation using one application-scoped async
      `httpx.AsyncClient` with an explicit bounded timeout; fail closed on timeout, connection error,
      or a malformed response. Remove `WorkspaceFsPort.delete` and its one caller
      (`AgentConfigAssetsAdapter` keeps its own team-scoped path/ReBAC, outside this contract).
- [ ] 2.5 Fix `LocalRegistryAgentInvoker.invoke` to preserve the parent's `(team_id,
      agent_instance_id, user_id, session_id)` binding onto a delegated child's execution request,
      replacing the current `agent_instance_id=None`. A child that cannot establish a consistent
      binding is refused Workspace access, not silently rescoped.
- [ ] 2.6 Regenerate generated clients: `cd apps/frontend && make update-knowledge-flow-api` and
      `make update-control-plane-api`. No hand-written DTO duplicates a generated type on either
      side.
- [ ] 2.7 Emit `workspace.binding_validation_latency_ms` using only the existing bounded `status`
      Prometheus label (never `trace_id`/`correlation_id`); confirm Grafana visibility per
      `OBSERVABILITY-AND-AUDIT.md`.
- [ ] 2.8 Cover isolation/actor-permission tests (RFC §9.1a, §9.7): human actor limited to
      `list`/`read`/`link` on their own subtree; agent M2M actor limited to its bound
      `(team_id, agent_instance_id, user_id)` subtree; a human JWT presented on the agent-write path
      is rejected outright, not merely left unauthorized; every RFC §9.5 fail-closed case (unknown
      session, id mismatch, disabled/suspended instance, wrong client identity, control-plane
      timeout/unreachable/malformed response) is exercised and refused.
- [ ] 2.9 Run `fred-performance-reviewer` and an independent `/code-review` on this phase alone before
      group 3 begins. Group 2 lands as its own commit — no Deep-side code in the same diff.

## 3. Add the thin Deep Workspace backend

Begins only once every group-2 task is complete, tested and reviewed; lands as its own commit,
separate from group 2, per RFC §9.10.

- [ ] 3.1 Implement `FredWorkspaceBackend` as an async `BackendProtocol` adapter over the bound
      `WorkspaceFsPort`: list, read, create-only Deep write over the Workspace create/replace
      primitive, edit by read/write, bounded glob and bounded literal grep. Translate only into
      Deep's existing result types.
- [ ] 3.2 Measure focused traversal behavior, choose explicit file-count and per-file byte limits,
      and cover success, missing path, oversized content, excessive traversal and partial failure.
- [ ] 3.3 Build `CompositeBackend(default=StateBackend(), routes={"/workspace/": ...})` in
      `DeepAgentRuntime` and pass it to `create_deep_agent`. Use no host filesystem, new client,
      sync-over-async bridge or parallel storage abstraction.
- [ ] 3.4 Remove the legacy filesystem-MCP-name gate made obsolete by the canonical backend. Prove
      `execute` is absent for the non-sandbox backend and no exposed tool ends in
      `NotImplementedError`.
- [ ] 3.5 Test path routing, async calls, same-binding next-turn reads, cross-binding failure and
      the StateBackend-versus-`/workspace/` ownership split.

## 4. Configure truthful publication for the Deep Assistant

- [ ] 4.1 Replace the Deep Assistant's unconditional “no filesystem tools” prompt text with runtime-
      truthful guidance: StateBackend scratch may exist, but durable/user-visible files require the
      scoped Workspace route and typed publication. Preserve fail-closed durable-file claims when
      that route is absent.
- [ ] 4.2 Declare the existing `artifacts.publish_text` tool as optional/selectable for the Deep
      Assistant scenario. Do not add a new publication or link tool in this slice.
- [ ] 4.3 Prove that publishing `deliverables/<name>` and reading
      `/workspace/deliverables/<name>` address the same authorized bytes, while `plan.md` and
      scratch are not automatically exposed as links.
- [ ] 4.4 Cover publication failure: no `LinkPart`, no success claim, unaffected artifacts retained.

## 5. Run the first acceptance proof

- [ ] 5.1 Configure the exact Deep profile, model and capabilities, then run the committed prompt
      without manual step splitting or mid-run prompt repair.
- [ ] 5.2 Verify `/workspace/plan.md` was updated and re-readable in the next turn; verify the CSV
      parses, contains every requirement, and all three final files are non-empty and consistent.
- [ ] 5.3 Verify persisted typed links survive history reload and authorization; confirm internal
      working files are not linked automatically.
- [ ] 5.4 Record revisions, configuration, metrics, rubric score and hard failures. The first proof
      requires at least 80/100 and zero hard failures, and must be described as one witnessed run
      using the public run-record template without raw private traces or real binding identifiers.

## 6. Quality, performance and durable documentation

- [ ] 6.1 Run focused tests and `make code-quality`/offline `make test` in every touched project.
- [ ] 6.2 Run `fred-performance-reviewer` on the Deep execution and composed traversal paths; verify
      no blocking I/O, per-call client construction or unbounded scan enters the hot path.
- [ ] 6.3 Run an independent `/code-review` and fix every blocking finding.
- [ ] 6.4 Update the compact runtime contract with the as-built backend ownership, traversal bounds,
      publication truth and tests. Trim/archive superseded RFC planning only when its remaining
      open work is genuinely closed.
- [ ] 6.5 Validate this OpenSpec strictly, report production/test/generated/documentation LOC
      separately, and identify the deleted legacy gate. Do not claim XLSX/DOCX, ReAct parity,
      sub-agent parity or repeated-run reliability.
