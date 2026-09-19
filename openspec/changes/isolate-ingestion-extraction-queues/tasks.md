One pull request, three commits, one per batch. Only batch 1 is implemented.

## 1. Batch 1 — Route extraction by profile

- [x] 1.1 Derive the per-profile extraction queue from the base task queue in one
      function used by both the submitting side and the worker, and verify the
      three profiles each get a distinct derived name.
- [x] 1.2 Carry the derived queue on `FileToProcess`, filled by the submission
      enrichment loop that already resolves the profile's timeouts and retries,
      and verify a mixed-profile submission routes each document to its own
      queue.
- [x] 1.3 Pass that queue to the push and pull extraction activities from their
      sub-workflows, leaving every other workflow and activity unrouted, and
      verify the workflow reads it from its payload rather than configuration.
- [x] 1.4 Remove the mixed-profile submission refusal and the root-workflow
      routing, and verify mixing push and pull is still refused.
- [x] 1.5 Fail a document whose payload carries no extraction queue with a
      non-retryable error, and verify it is an `ApplicationError` so the workflow
      fails instead of the workflow task retrying forever.

## 2. Batch 1 — Specialize the worker by role

- [x] 2.1 Configure the roles a worker process serves, defaulting to all four so
      a single process still consumes every queue, and verify an empty or
      repeated role list is refused.
- [x] 2.2 Build one Temporal worker per role from a single registration
      definition, and verify the common role registers every workflow and no
      extraction activity while an extraction role registers the two extraction
      activities and no workflow.
- [x] 2.3 Sync the recurring maintenance schedules only from the common role,
      without adding a flag or a leader election, and verify an extraction-only
      worker posts none and that a sync failure still lets the worker serve.
- [x] 2.4 Verify the non-ingestion workflows — revectorize, vector-metadata
      repair, fast vectors, PDF-render expiry — stay registered on the common
      role.
- [x] 2.5 Log the role, the queue polled, the activity concurrency and, for the
      common role, the workflow-task concurrency at worker startup.

## 3. Batch 1 — Deployment and configuration

- [x] 3.1 Configure four worker deployments in the chart, one per role, reusing
      the existing worker block and replacing only the scheduler block and the
      pod resources, and verify the render produces four deployments whose
      polled queues match the routing.
- [x] 3.2 Set one concurrent extraction per rich pod and bounded, configurable
      concurrency for the other groups, and verify the rendered values.
- [x] 3.3 Set CPU, memory and docling thread counts coherently per group, and
      verify threads x concurrency does not exceed each group's CPU limit.
- [x] 3.4 Register the new deployments in the chart schema generator and
      regenerate both generated schemas through the repository procedure.
- [x] 3.5 Verify the checked-in configuration files still validate and that the
      single-process developer worker still serves every queue.
- [x] 3.6 Give the k3d overlay's single worker pod all four roles, and verify the
      local and bench renders consume every queue their values route to.
- [x] 3.7 Share the four groups' Temporal connection, base queue, storage and
      image through render-time inheritance rather than YAML anchors, and verify
      with a render using non-standard values that an override of the common
      worker reaches all four.
- [x] 3.8 Refuse to render when the enabled workers leave a role unserved, and
      verify that enabling the historical worker alone fails with an actionable
      message while a single all-roles worker still renders.
- [x] 3.9 Render a whole retuned ingestion deployment, API included, and verify
      the API and the four worker groups come out with one Temporal server,
      namespace, base queue, content storage and document destination while each
      group keeps its own role and concurrency; state in the chart where the API
      and the workers' common base are each configured, without implying that
      overriding one configures the other.

## 4. Batch 1 — Verification

- [x] 4.1 Run the scheduler and worker test modules and verify all pass, the
      extraction sub-workflows' actual `execute_activity` calls included, for the
      three profiles on both the push and the pull path.
- [x] 4.2 Run `make code-quality` and `make test` from
      `apps/knowledge-flow-backend` and verify both complete successfully.
- [x] 4.3 Run an independent cold-diff review of the change and record the
      findings or confirm none remain.
- [x] 4.4 Run `openspec validate isolate-ingestion-extraction-queues --strict`.
- [x] 4.5 Update GitHub issue #2762 to the agreed design.

## 5. Batch 2 — Document robustness and independence (not started)

- [ ] 5.1 Bound document admission so fast documents do not wait behind rich ones
      within a batch.
- [ ] 5.2 Match execution deadlines to each stage.
- [ ] 5.3 Review heartbeats and bound retries per stage.
- [ ] 5.4 Verify replayed operations are idempotent.
- [ ] 5.5 Make cancellation actually stop computation on the extraction pods.
- [ ] 5.6 Verify terminal states stay coherent on failure and on cancellation.

## 6. Batch 3 — Observability and load validation (not started)

- [ ] 6.1 Separate waiting from running explicitly for each major stage.
- [ ] 6.2 Emit KPIs per queue, stage and profile.
- [ ] 6.3 Build a dashboard that locates a blockage.
- [ ] 6.4 Measure CPU, memory, restarts and OOM per worker group.
- [ ] 6.5 Run a reproducible local campaign with representative documents.
- [ ] 6.6 Replace this change's starting resource hypotheses with measured
      sizing.
- [ ] 6.7 Write the operating documentation and finalize these artifacts.

## Verification Evidence

Batch 1, recorded before the first commit and before an independent audit.

- Unit tests: `tests/features/scheduler/` and `tests/core/test_main_worker.py`,
  114 passed. These cover the routing derivation, the per-document enrichment,
  the workflow's payload guard, the per-role registrations and queues, the
  schedule ownership, and the role-list validation. Six of them run
  `PushInputProcess.run` and `PullInputProcess.run` on a payload built by the
  real submission path, with `workflow.execute_activity` intercepted, and assert
  the activity scheduled is `push_input_process` / `pull_input_process` on
  `ingestion-fast` / `-medium` / `-rich` respectively; a seventh asserts the
  profile's timeouts still reach that same call.
- Helm render, `make check-chart-ingestion-workers` (four checks, all passing,
  wired into the `deploy-charts-checks` CI job). The first two prove two
  different agreements and are deliberately separate:
  - **Propagation between worker groups.** An override of the common worker's
    Temporal host, namespace, base task queue, content storage and image — all
    values chosen not to match anything in `values.yaml` — reaches all four
    rendered groups, while their roles stay `common` / `extraction-fast` /
    `extraction-medium` / `extraction-rich` and the rich group keeps one
    extraction per pod. This says nothing about the API, which inherits nothing
    from the workers.
  - **Agreement between the API and the workers.** A whole ingestion deployment
    retuned off the chart defaults — the API and the four worker groups, the API
    configured explicitly because nothing propagates to it — renders with one
    Temporal server, one namespace, one base task queue, one content storage
    bucket and one vector store index across all five applications, while each
    worker group keeps its own role and its own activity concurrency (3 / 4 / 2 /
    1). Verified to be a real check, not a vacuous one: removing the API from
    that overlay makes it report all five settings the API then diverges on,
    rather than passing or raising.
  - Enabling the historical worker alone is refused, naming the three unserved
    extraction roles.
  - A single worker declaring all four roles renders.
- Helm render, by hand: `helm lint` clean; the four deployments render with
  concurrencies 3 / 4 / 2 / 1 and resources 2 CPU·4Gi, 2 CPU·4Gi, 4 CPU·8Gi and
  4 CPU·12Gi; docling threads are 2 for medium and 4 for rich, so threads x
  concurrency is 4 on both docling groups, matching their 4 CPU limits. The k3d
  local and bench overlays render a single worker serving all four roles.
- Configuration and quality: `make check-config-files` passes for all four
  checked-in knowledge-flow configuration files; `make check-chart-values` and
  `make check-chart-schema-drift` pass; `make code-quality` passes with
  Basedpyright reporting 0 errors, 0 warnings, 0 notes; `make test` passes with
  1221 passed, 27 deselected.
- Independent cold-diff review: six findings, five fixed. The k3d overlay
  enabled only the old worker and would have left the three extraction queues
  unpolled; the worker's several roles are now supervised by a task group so one
  failing role cancels the others before the caller tears the database engine
  down; the per-role concurrency multiplication and the shared docling-thread
  anchors are now stated where they are configured. The sixth — no replay gate
  for workflows already in flight — is the migration case this change
  deliberately does not handle, recorded as a deployment constraint above.
- Audit follow-up: YAML anchors were carrying the four groups' shared
  configuration, and an anchor cannot carry a values override, so a retuned
  Temporal server or base queue would have reached the common worker alone.
  Replaced by render-time `inheritFrom` inheritance plus the role-coverage
  refusal, both covered by the check above.
- **Not executed: real Temporal.** No run against a live Temporal server. This
  repository has no Temporal integration test —
  `tests/features/scheduler/test_workflow.py` records that the `@workflow.defn`
  classes need a live test environment that is not used here. What that leaves
  unproven, precisely:
  - The activity-call tests intercept the SDK rather than reaching a server, so
    they prove what the workflow asks for, not that a worker polling that queue
    picked it up.
  - The chart checks read rendered YAML, so they prove the five applications are
    configured to agree, not that a document submitted by the API was extracted
    on a profile's pods and indexed back on the common ones.
  - The hand-off between queues — extraction restoring its input, and indexing
    restoring extraction's output, from shared content storage on another pod —
    is established by reading the code paths, not by execution.
  An end-to-end run belongs to batch 3's load campaign, which is where a
  representative corpus and real pods exist.
