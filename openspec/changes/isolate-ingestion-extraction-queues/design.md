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
- **A batch still blocks on its slowest document.** `_wf_run_parent_pipeline`
  starts documents in batches of `max_parallelism` and waits for all of them, so
  a rich document still delays the fast ones submitted alongside it. Unchanged
  here on purpose — that is batch 2.
