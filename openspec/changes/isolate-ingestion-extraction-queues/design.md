## Context

See `proposal.md` for the production problem. The ingestion pipeline is a
parent workflow (`ProcessPush` / `ProcessPull`) that starts one child workflow
per document (`ProcessPushFile` / `ProcessPullFile`), which in turn runs three
sub-workflows: metadata, extraction (`PushInputProcess` / `PullInputProcess`),
and indexing (`OutputProcess`). Every one of them currently inherits the root
workflow's task queue, because none declares one.

Extraction is the only stage whose cost depends on the profile in a way a pod
boundary can isolate: its CPU and memory footprint follows the profile's
extractor, OCR and image settings. Indexing is not free — chunking and its
per-chunk work scale with the document's volume, and the rich profile generates
a summary there, several model calls over the whole text — but its cost follows
the document, not a per-profile extractor configuration, and it is the same code
on every profile.

We run on Kubernetes Autopilot. Resources and replica counts are adjustable, so
the useful unit of isolation is the pod, not a finer split of the pipeline.

## Goals / Non-Goals

**Goals:**

- Keep the existing workflows, sub-workflows, activities and their sequencing.
- Keep the existing save and restore through shared content storage.
- Move only extraction off the common queue, per document.
- Give each profile its own deployment, sized and bounded independently.
- Make the effective configuration of a running worker readable from its logs.

**Non-Goals:**

- Merging or further splitting activities.
- Changing timeout and retry policies, cancellation, or the batched document
  admission — batch 2.
- KPIs per queue and stage, dashboards, load measurement — batch 3.
- Autoscaling or dynamic allocation of any kind.
- Supporting workflows already in flight when the change is rolled out.
- A fifth queue, a priority system, or a generic routing framework.

## Decisions

### Route the activity, not the workflow

The two extraction activities pass an explicit `task_queue`; nothing else does.
Everything else — the root workflow, all sub-workflows, metadata, progress
events, indexing, maintenance — inherits the common queue as it does today.

The alternative, routing the root workflow by profile, was the original plan on
issue #2762 and is rejected. It sends a document's entire pipeline to the
dedicated pods, which means those pods must register every workflow and every
activity, and it makes one submission belong to one queue: a batch mixing
profiles then has to be refused, or the routing pushed down into the child
workflows anyway. Routing the activity is both narrower and more permissive.

### The queue travels in the document payload

`FileToProcess` gains `extraction_task_queue`, filled at submission time by
`IngestionTaskService.submit_documents`, next to the timeouts and retry settings
that same loop already derives from the profile. The workflow reads it from its
payload.

A workflow must not read deployment configuration: that is a source of
non-determinism on replay. Reusing the enrichment loop that is already the place
where a profile becomes concrete per-document settings adds no new mechanism.

Missing means the submission did not route the document. The workflow then
raises a non-retryable `ApplicationError` rather than omitting `task_queue` and
inheriting the common queue, where extraction is not registered: the activity
would sit there until its start-to-close timeout with nothing in the logs.
`ApplicationError` specifically, because only a `FailureError` fails the
workflow — any other exception fails the workflow *task*, which Temporal retries
forever while the document still reads as running.

### One derivation function for the queue name

`extraction_task_queue(base_task_queue, profile)` returns
`f"{base}-{profile}"`. The submitting side calls it per document; the worker
calls it for the role it serves. Two sides spelling a queue name by hand is how
submissions disappear silently, so neither side spells one.

### The worker's role decides both its queue and its registrations

`scheduler.worker_roles` names the roles a worker process serves. The common
role registers every workflow and every activity but extraction and polls the
base queue; an extraction role registers the two extraction activities, no
workflow, and polls its profile's queue. One function builds a worker from a
role, so the full registration list is written once.

It is a list rather than a single role because a Kubernetes deployment declares
exactly one, while a developer runs a single process: the default is all four
roles, one Temporal worker each in the same process, which is exactly today's
behaviour and leaves `make run-worker` and the checked-in `config/*.yaml`
untouched. An empty or repeated list is rejected at configuration load.

`ingestion_max_concurrent_activities` is a limit per Temporal worker, therefore
per role. A deployment serving one role reads it as the pod's limit; a process
serving several multiplies its simultaneous capacity by the number of roles. The
process logs that total at startup so the multiplication is visible where it
happens rather than inferred from the configuration.

### Maintenance schedules are the common role's, by derivation

`sync_pdf_render_expiry_schedule` targets `config.task_queue`, the base queue,
and posts a workflow only the common role registers. Only a process serving the
common role syncs it. No flag: a separate "owns the schedules" setting could
contradict the role, and every value of it that is not implied by the role is a
misconfiguration. Replicas of the common deployment all sync the same
definition, which is what they already do today, so no leader election is
introduced.

### The four deployments share their configuration at render time, not by anchor

A YAML anchor is resolved when the file declaring it is parsed. Helm merges every
`-f` values file and `--set` afterwards, so an anchor cannot carry an override:
retuning `applications.knowledge-flow-worker`'s Temporal host, base queue,
content storage or image would have reached that one deployment and left the
three extraction deployments on the values baked into `values.yaml`. A base-queue
mismatch loses every submission, since the queue name is derived from it.

Each extraction deployment therefore declares `inheritFrom: knowledge-flow-worker`
and `main.yaml` deep-merges the named application underneath it, after Helm has
merged everything. `main.yaml` is the only template that iterates `applications`,
so one place covers image, dotenv, volumes and the whole configuration. The key
is generic, not ingestion-specific, and applications that do not declare it are
untouched.

This covers the four worker groups and nothing else. `knowledge-flow-backend` is
a separate application that inherits nothing from them, and it is the one that
derives each profile's extraction queue name when it submits and writes the
uploaded document to content storage before any worker reads it. An overlay
retuning ingestion therefore configures two applications, the API and the common
worker, and the chart does not paper over that: no mechanism makes an override of
the worker reach the API. Making the API inherit from the worker, or the reverse,
was rejected — they are different processes with different responsibilities, and
an inheritance edge between them would hide, rather than surface, the one
agreement that actually has to hold. The whole-deployment render check is what
holds it instead.

The chart then refuses to render when the enabled knowledge-flow workers do not
cover the four roles between them. It identifies a worker by the entrypoint its
command runs, not by its name. This is what stops a values file that predates
this change — enabling `knowledge-flow-worker` alone — from quietly becoming a
common-only deployment with three unserved extraction queues. A single process
declaring all four roles passes it, which is how the local cluster runs.

### Shared storage is unchanged, and is what makes the split safe

Extraction already restores its input from content storage
(`resolve_push_input_file_for_worker` for push, the content loader for pull) and
writes its result back with `save_output`. `ProcessPushFile` passes an empty
`input_file`, so the local fast path is never taken on this route. Indexing
restores that result with `get_local_copy`. No step depends on a temporary file
left behind by the pod that ran the previous one, and no file content travels
in a Temporal payload. Nothing here needed changing; it needed verifying.

## Risks / Trade-offs

- **In-flight workflows break.** A workflow started before the rollout replays a
  history whose extraction command carries no task queue, and its payload has no
  `extraction_task_queue`. Deliberately not handled, per the agreed scope:
  ingestion must be drained before rolling out.
- **A queue with no consumer never resolves itself.** An activity nobody polls is
  never started, and `start_to_close_timeout` only runs from the moment a worker
  starts it; the pipeline sets no `schedule_to_close_timeout`, so the document
  waits indefinitely rather than failing. The chart therefore refuses to render
  when the enabled workers do not cover the four roles between them, which is
  where this is caught. Nothing detects it at runtime yet — batch 3.
- **One extraction per rich pod is not an OOM guarantee.** It bounds how much a
  single document may take, but a large enough PDF still exhausts the pod alone.
- **Resource values are hypotheses.** CPU is derived from
  `docling_num_threads x ingestion_max_concurrent_activities`; memory is a
  guess, widest for the rich group. Batch 3 replaces them with measurements.
- **A batch still blocks on its slowest document.** Resolved in batch 2 below.

## Batch 2 decisions — document independence and robustness

### Per-profile admission windows in the existing parent

`_wf_run_parent_pipeline` replaces its fixed batches with one admission loop.
It keeps a count of in-flight children per profile, starts the *first admissible*
document rather than the head of the queue, and waits on `workflow.wait` — the
SDK's deterministic variant — for a child to finish before admitting again.

- **Individual bound**: `P = ingestion_workflow_parallelism` per profile.
- **Total bound**: `T = P x the number of profiles present in the submission`.

A fast document in position 10 therefore starts while three rich documents in
positions 0-2 occupy the rich window, and a freed slot is reused on the next
turn of the loop rather than at the end of a batch.

A single shared window was rejected: it can be filled entirely by rich documents,
which is the very starvation this batch removes. `T < sum(P)` was rejected too —
it reintroduces cross-profile contention in the parent, which batch 1 removed
from the pods. Contention belongs in the worker pools, where it is isolated by
construction.

Note the change of meaning: `ingestion_workflow_parallelism` becomes a per-profile
ceiling, so one submission may hold up to 3P open children instead of P. The extra
children wait in their profile's extraction queue, which is what that queue is for.

### Per-document failure containment

Each child runs inside a wrapper that catches its failure and returns an outcome,
the shape `RevectorizeDocument` already uses. A failed document no longer aborts
its siblings or the documents not yet admitted.

Cancellation stays distinct: `asyncio.CancelledError` is a `BaseException` and so
passes through `except Exception` untouched, and the Temporal-shaped cancellation
is re-raised on `is_cancelled_exception`. Cancelling therefore still stops
admission, while a failing document does not.

It reaches the parent two ways, and both leave the loop the same way: a child
reporting it, and the cancellation landing on the parent itself while it waits.
The admission loop is therefore wrapped as a whole — on any way out that is not
the loop finishing, the documents still running are cancelled and every outcome
is collected. Collected because an unretrieved task exception is logged later as
an unhandled error, on the very path already reporting the cancellation; and a
second cancellation arriving during that collection is absorbed rather than
allowed to leave it half-done, the first one being re-raised regardless.

The documents in flight are held in a list, in admission order, and
`workflow.wait`'s lists are kept as they come back. A set would be iterated in
address order, and since everything this loop does with a child ends up as a
Temporal command — starting it, cancelling it — a replay after a worker restart
could not reproduce that order. `workflow.wait` exists in the SDK for exactly
this reason; passing it a set would have given that back.

The parent returns `{total, processed, failed}` instead of the constant
`"success"`, and completes normally even when documents failed. It does not raise:
a raising parent is indistinguishable from a crash or a cancellation, and it would
not change any document's outcome. This matches `RevectorizeCorpusWorkflow` — the
workflow completes, the task carries the verdict.

Reconciliation is unchanged and already covers the remaining gap. A document whose
terminal event could not be persisted stays pending; the parent completes; the
sweeper (started in the API lifespan, 120s interval, 300s grace) reads
`completed` and records "Execution finished without completing the task". A
document whose event was persisted is already terminal and is left alone. The one
residual false negative — a document that succeeded but whose terminal event never
persisted — is reconciled to `failed`; bounded retries on the event activity make
it unlikely, and removing it entirely would mean teaching the reconciler to read
the workflow's return value, a new contract.

Raising the event activity's attempts is safe because the write is idempotent in
effect: `record_event` assigns `run.state` and `detail` absolutely rather than
incrementally, the per-document counters are absolute with `total=1`, and
`repair_document_after_terminal` is idempotent by construction. Only `seq`
advances, so a duplicate reaches the SSE stream twice with identical content.

### Execution budgets that exclude queue wait

`schedule_to_close_timeout` includes the time an activity spends waiting in its
queue; `start_to_close_timeout` does not. Metadata, indexing and progress events
used the former, so a saturated queue consumed the budget meant for execution and
the activity could fail without ever starting. They move to `start_to_close`,
per attempt, with bounded attempts sized to the operation rather than inherited
from the extraction profile.

The trade-off is explicit: there is no longer a single ceiling over all attempts.
The worst case becomes `attempts x per-attempt budget`, which is the intended
reading — a heartbeat proves contact, not progress, so a per-attempt maximum has
to stay.

Permanent errors are expressed as `ApplicationError(non_retryable=True)` at the
point they are detected, the idiom `raise_if_document_deleted` already uses, rather
than by growing `retry_non_retryable_error_types` lists in configuration.

This required narrowing one wrapper first: the input restore paths turned *any*
exception into `FileNotFoundError`, so a transient object-store outage was
indistinguishable from a genuinely missing file. A missing input is now permanent
and anything else stays retryable.

### Extraction runs in a killable local process

Cooperative cancellation cannot stop an extraction. The only checkpoints in the
codebase are in vector indexing, and the extractors expose no loop boundary to add
one to: docling is a single `convert()` call per document and pymupdf4llm a single
`to_markdown()`. Draining the thread under a bound does not fix it either — when
the bound expires the thread is still running while its Temporal slot has been
returned, so a new extraction starts on a pod that is still busy.

Extraction therefore runs in a child process the activity can kill.

**Boundary.** The narrowest existing one is the pipeline, not the service.
`IngestionService.__init__` builds the content store and `MetadataService`, which
pull in further services; the child must not construct it. `ProcessingPipelineManager`
needs only the configuration and the processor classes — no store, no database, no
object storage. The extraction body moves to `ProcessingPipelineManager.run_input`,
called by `IngestionService.process_input` as before and by the child directly, so
there is one implementation and no duplicated pipeline selection.

The profile survives the boundary: the child re-enters `processing_profile_scope`,
so the effective per-profile settings — extractor, OCR, docling threads,
`process_images` — are the ones the processors read. Rich extraction's external
calls (the vision model describing images) work because the child inherits the
parent's environment. Nothing sensitive is passed as a command argument or logged.

**What crosses.** To the child: input path, output directory, the document metadata
as JSON and the profile name. From the child: an exit status and a structured error.
The extraction's real output is the files it writes into the output directory, which
parent and child already share — no result is marshalled.

**Process creation.** `spawn`, not `fork`: forking a process that holds the Temporal
worker's event loop, its gRPC client and a thread pool copies locks in unknown
states. The cost is the child's interpreter start and imports, to be measured
locally rather than guessed. No pool: a rich pod runs one extraction at a time, so
a pool of one is not a pool, and a pool would bring back the cross-document state
this boundary exists to remove.

**Stopping.** The child leads its own process group, and the activity signals the
group rather than the process, so descendants are covered without enumerating
them. `SIGKILL` directly, with no `SIGTERM` grace period: extraction has nothing
to flush — its output goes to a directory the parent is about to discard — so a
polite shutdown would only delay the moment the CPU comes back. The group is
signalled on the normal path too: a child that ended by itself, successfully or
not, can have left a helper behind holding the pod.

The activity waits for that — without blocking the event loop, there as much as
during the extraction itself — and only then removes the temporary directory and
releases its Temporal slot. That ordering is what removes the overlap: the slot
is never free while the computation is not.

The stop cannot be abandoned half-way. It runs as its own task behind a shield,
so an activity cancelled *again* while it is already cancelling re-enters the
wait instead of returning with the computation still running, and the supervisor
returns only once that task is done — never leaving it to finish in the
background.

**When the stop cannot be confirmed.** Only an uninterruptible kernel operation
survives `SIGKILL`, so a child still alive after the reap timeout means the pod
is sick, not the document. The activity then fails with `ExtractionStopUnconfirmed`
in place of whatever it was about to report — a success, a budget timeout, even a
cancellation — because every one of those tells Temporal this worker is free to
take the next extraction. Making the *worker* act on it (stop polling, or fail
its liveness probe so the pod is replaced) would be a new worker-level policy and
is deliberately not in this change.

Temporal's own timeout is not part of this. An expiring `start_to_close_timeout`
fails the attempt on the server; the worker learns of it through a heartbeat
response, or not at all. The activity therefore enforces its own budget, derived
from the profile's timeout minus the time already spent and minus a reserve for
the shutdown itself, and the Temporal timeout goes back to being the backstop for
a worker that has died. That budget has no floor: when nothing is left once the
reserve is kept, the attempt is refused before a child exists, rather than
starting an extraction it could only kill part-way through.

`PR_SET_PDEATHSIG` covers the one case the activity cannot: the worker being
`SIGKILL`ed, which runs no `finally`. It is best-effort and Linux-only, and it
applies to the child alone — a descendant of the child is not covered by it,
which is why the group signal remains the primary mechanism. Its own race is
covered by the child comparing its parent against the identity it was started
with, not against pid 1: the parent can die between the fork and the `prctl`
call, and under a subreaper — or in a container whose pid 1 is the worker itself
— a re-parented child never sees `getppid() == 1`.

**Not claimed.** Across a network partition, two workers can hold the same
activity attempt. Nothing here prevents that and nothing here makes it safe:
both children extract the same document and write to the same shared-storage
keys, so which output survives is decided by arrival order, and a reader in
between can see one attempt's output mixed with the other's. Excluding it needs
a lease or a fencing token on the document, which this change does not add.
