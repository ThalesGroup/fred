One pull request, three commits, one per batch. Batches 1 and 2 are implemented.

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

## 5. Batch 2 — Document robustness and independence

- [x] 5.1 Replace the parent's fixed batches with a bounded admission window per
      profile, admitting the first admissible document rather than the head of
      the queue, and verify a fast document starts while the rich window is full
      and that a freed slot is reused immediately.
- [x] 5.2 Contain a document's failure so its siblings and the documents not yet
      admitted keep going, and verify cancellation still stops admission.
- [x] 5.3 Return the submission's tally from the parent instead of a constant,
      completing rather than raising, and verify the existing reconciliation
      still drives a document whose terminal event was lost to a terminal state.
- [x] 5.4 Give metadata, indexing and progress events per-attempt execution
      budgets that exclude queue waiting, with bounded attempts sized to the
      operation rather than inherited from the extraction profile.
- [x] 5.5 Narrow the input-restore wrapper so a missing input stays permanent and
      a transient storage failure stays retryable.
- [x] 5.6 Run extraction in a killable child process through the narrowest
      existing boundary — the pipeline manager, not the ingestion service — and
      verify the profile and its effective settings survive the boundary.
- [x] 5.7 Supervise that process without blocking the event loop, heartbeating
      throughout, on a budget derived from the attempt's own deadline minus the
      time already spent and a shutdown reserve.
- [x] 5.8 Terminate the child's process group and confirm it is reaped before
      removing the working directory or finishing the activity, and verify with a
      test child that starts its own descendant.
- [x] 5.9 Keep the five outcomes apart across the process boundary: permanent
      document error, transient failure, budget timeout, cancellation, abnormal
      exit.
- [x] 5.10 Add `make run-worker-role ROLE=...`, deriving a temporary
      configuration from the existing local one rather than committing four
      copies.

## 6. Batch 2 — Verification

- [x] 6.1 Run the scheduler test modules and verify all pass.
- [x] 6.2 Run `make test` in `apps/knowledge-flow-backend` and `make
      code-quality` from the repository root, and verify both complete.
- [ ] 6.3 Run the local scenarios S1-S8 against real Temporal and workers, and
      record what they showed.

## 7. Batch 3 — Observability and load validation (not started)

- [ ] 7.1 Separate waiting from running explicitly for each major stage.
- [ ] 7.2 Emit KPIs per queue, stage and profile.
- [ ] 7.3 Build a dashboard that locates a blockage.
- [ ] 7.4 Measure CPU, memory, restarts and OOM per worker group.
- [ ] 7.5 Run a reproducible local campaign with representative documents.
- [ ] 7.6 Replace this change's starting resource hypotheses with measured
      sizing.
- [ ] 7.7 Write the operating documentation and finalize these artifacts.

## Verification Evidence — batch 1

Recorded before the first commit and before an independent audit.

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

## Verification Evidence — batch 2

Recorded before the second commit and before an independent audit.

- Unit tests, simulated: `tests/features/scheduler/test_parent_admission.py`
  (6) runs `_wf_run_parent_pipeline` itself with `start_child_workflow`
  intercepted, driving each child by hand. It shows a fast document starting
  while the rich window is full, a freed slot reused without waiting for the
  other profiles, per-profile and total bounds held, a failed document leaving
  its siblings and successors running, the tally reporting the failure, a
  cancellation reported by a child stopping admission instead of counting as
  one, and a cancellation landing on the parent itself stopping admission and
  taking its running documents with it.
- Unit tests, real processes: `tests/features/scheduler/test_extraction_process.py`
  (27) starts actual child processes and signals them. It shows the child and a
  descendant it started both stopped and reaped, a descendant left behind by a
  child that ended on its own stopped too, the local budget stopping the child
  itself, an exhausted attempt starting no process at all, cancellation during
  start-up leaving nothing running, a second cancellation landing inside the
  stop without abandoning it, an unconfirmed stop overriding both a timeout and
  a cancellation, heartbeats continuing throughout, the event loop staying
  responsive during the wait *and* during the stop, the start-up parent-identity
  guard refusing to run, one child started and stopped through the production
  `spawn` method, and the five outcomes staying apart.
- Every one of the four behaviours the second audit asked for was checked
  against a mutant: reverting the descendant sweep, the parent-identity guard,
  the parent's cancellation drain and the unconfirmed-stop refusal each fails
  exactly the test written for it and nothing else.
- Whole suite: **to re-run.** `make test` in `apps/knowledge-flow-backend` and
  `make code-quality` from the repository root were last run before the second
  audit (1246 passed / clean). Since then, run here directly:
  `tests/features/scheduler`, `tests/features/ingestion` and `tests/core` —
  278 passed; `ruff check` and `ruff format --check` clean on the touched
  files; `basedpyright` over the whole backend — 0 errors, 0 warnings, 0 notes.
- Three defects were found by these tests rather than by reading, and fixed:
  - `killpg` on a child that had not yet reached `setsid()` targeted the
    worker's own process group. A cancellation landing in that window would have
    killed the worker, its siblings' extractions and its Temporal client. The
    group is now compared with our own before being signalled, and the child
    creates its group before doing anything else.
  - A pipe left by a child killed before it wrote polls ready and then raises;
    an OOM-killed extraction would have surfaced as an unhandled `EOFError`
    instead of an abnormal exit.
  - A single `asyncio.shield` does not protect an await that is itself cancelled
    again, so a second cancellation abandoned the stop and returned — reporting
    a free slot while the extraction was still running. The stop is now its own
    task, and the supervisor re-enters the shielded wait on every cancellation
    until that task is done.
- Independent cold-diff review: six findings, all six fixed.
  - The progress-event activity also runs the terminal document repair, which on
    a cancellation erases the document's content, vectors, metadata and quota. A
    30-second budget would have truncated that on a large document and retried
    the erasure from the start without ever persisting the terminal event.
  - The pull metadata activity downloads the whole source file before reading it,
    so it is not the catalog lookup the push one is and does not share its budget.
  - The two extraction activities are also called in-process by the synchronous
    upload path and by library sync, inside the API. They now only use a child
    process inside a Temporal activity: elsewhere there is no worker slot to keep
    honest, and spawning an interpreter per uploaded document would cost a great
    deal for nothing.
  - The process group was read after the child had been reaped, so the sweep for
    descendants never ran and a recycled pid could have been signalled. It is now
    captured while the child is alive.
  - Admission bucketed on the raw profile while the queue came from the
    normalized one, so a submission mixing explicit and implicit profiles opened
    two windows onto one queue. It now buckets on the extraction queue itself.
  - A cancellation left its siblings' exceptions unretrieved.
- Second developer audit of batch 2: four areas, all addressed before any
  commit.
  - The parent handled a cancellation reported by a child but not one landing
    on itself in `workflow.wait`: it propagated with its children still running
    and their outcomes unread. The admission loop is now wrapped as a whole and
    the running documents are cancelled and collected on any way out.
  - The stop blocked the event loop on `process.join()` — the very thing the
    wait around the extraction exists to avoid, on the path where the worker is
    already cancelling. It is now an awaited poll, re-entered through a shield
    on each further cancellation, and never left to finish in the background.
  - A stop that could not be confirmed returned as if the pod were free. It now
    fails with `ExtractionStopUnconfirmed` instead of the success, timeout or
    cancellation it was about to report. Making the *worker* act on that is a
    new worker-level policy and is deliberately left out — see design.md.
  - A child that ended on its own could leave a descendant running. The process
    group is now signalled on that path too, and the group is latched while the
    child is still alive so it can still be looked up once the child is reaped.
  - The local budget had a 30-second floor, which extended an extraction past
    the attempt's own deadline. The floor is gone; an attempt with nothing left
    after the shutdown reserve is refused before a child is created. The test
    that asserted the floor asserted the defect and has been replaced.
  - The `PR_SET_PDEATHSIG` start-up race was detected with `getppid() == 1`,
    which misses a re-parented child under a subreaper or when pid 1 is the
    worker. The child now compares against the identity it was started with.
  - The claim that last-writer-wins made two concurrent attempts harmless was
    removed from the module and from design.md; the limitation is stated
    instead, with no distributed protocol added in this batch.
  - The tests forked while production spawns. One test now starts and stops its
    child with `spawn` (2.7s) so the shipping path is exercised.
- Independent cold-diff review of the audit round: one finding fixed, six
  recorded below and left to a decision.
  - Fixed: the documents in flight were held in a `set`, so the order the parent
    starts and cancels them in — every one of which is a Temporal command — was
    address order, which a replay after a worker restart cannot reproduce.
    `workflow.wait` returns lists for precisely this reason. Now a list
    throughout, and the test double reproduces the SDK's list semantics rather
    than `asyncio.wait`'s sets.
- Open, from that same review — none of them introduced by the audit round, all
  needing a decision rather than a patch:
  - **`spawn` costs 7.5s of imports per document** (measured: the child's three
    imports, cold). On the fast profile that can exceed the extraction. Batch 3
    measures it; `forkserver` or a reused supervised child would keep the
    kill-ability without paying it per document.
  - **Per-image OCR/VLM KPIs are lost for Temporal ingestion.**
    `PdfMarkdownProcessor._pdf_kpi_timer` gates on `activity.in_activity()`,
    which is false inside the extraction child, so it returns a null context.
    This is exactly the data batch 3 needs to replace the guessed pod sizes.
  - **The child does open a content store.** `ExcelProcessor._register_tables`
    calls `get_content_store()` during the input stage, so the "no store, no
    database, no object storage" claim above holds for the pipeline manager but
    not for every processor it runs.
  - **The metadata sub-workflows lost the profile's retry policy** (task 5.4):
    `_SHORT_OPERATION_RETRY` gives up ~3s after the first failure where the
    profile's gave ~30 minutes. `create_pull_file_metadata` downloads the whole
    source file, so a source outage of a minute now fails the document.
  - **`OutputProcess` has no total cap any more**: one hour per attempt times
    six attempts, where `schedule_to_close_timeout` used to bound the whole
    thing at one hour.
  - **The admission loop is O(n²)** — `pending` is copied and `list.remove`d once
    per completed document, inside the single-threaded workflow loop. Visible
    only on a large library sync.
- Not executed: the local scenarios below, and anything against a real Temporal
  server. What the unit tests establish is that the supervisor stops a process
  and that the parent admits documents as described; they do not establish that
  a cancelled *docling* extraction releases the pod's memory, that a worker
  killed with SIGKILL leaves no extraction behind, or that an indexing retry
  does not re-run extraction. Those need the running stack.

## Local scenarios for batch 2

Run with four separate worker processes — a single multi-role worker cannot show
memory isolation:

```
make run-worker-role ROLE=common     # metrics 9112
make run-worker-role ROLE=fast       # metrics 9113
make run-worker-role ROLE=medium     # metrics 9114
make run-worker-role ROLE=rich       # metrics 9115, one extraction at a time
```

| # | Scenario | What to do | Evidence |
| --- | --- | --- | --- |
| S1 | Rich before fast | `scripts/submit_mixed_profiles.py` with 3 rich then 5 fast | The fast tasks reach `succeeded` while the rich are still `running` |
| S2 | One document fails | Same submission with one 0-byte PDF | Its task fails, the others succeed, the parent workflow is Completed with `failed: 1` |
| S3 | Cancel an extraction | Cancel once the rich worker logs its child pid | The child process disappears; the pod's CPU drops; never two extraction children at once |
| S4 | Kill a worker | `kill -9` the rich worker mid-extraction | No orphan extraction child survives; after restart the document completes |
| S5 | Indexing outage | Stop OpenSearch after extraction succeeded | No second extraction is logged; indexing retries and completes; no duplicate chunks |
| S6 | Local budget expires | A rich document past its derived budget | The activity kills the child itself and reports a timeout, before Temporal times the attempt out |
| S7 | Cancel right after start | Cancel within a second of the extraction starting | No child is left running, and the worker itself is still alive |
| S8 | Kill a worker with a descendant | `kill -9` the worker while an extractor helper is running | Neither the child nor its descendant survives |
