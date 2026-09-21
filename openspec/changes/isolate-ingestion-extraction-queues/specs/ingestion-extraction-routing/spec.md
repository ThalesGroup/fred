## Purpose

Defines how a document's processing profile decides which Temporal queue and
which worker pods run its extraction, what each worker role registers, and what
stays on the common queue.

## ADDED Requirements

### Requirement: Extraction is routed by processing profile
Knowledge Flow SHALL run the push and pull extraction activities on a Temporal
task queue derived from the document's processing profile, and SHALL derive that
queue name from the configured base task queue on both the submitting side and
the worker side.

#### Scenario: A rich document extracts on the rich queue
- **WHEN** a document with the `rich` profile is submitted for ingestion
- **THEN** its extraction activity is scheduled on the queue derived for `rich`
  from the configured base task queue

#### Scenario: Each profile has its own extraction queue
- **WHEN** documents with the `fast`, `medium` and `rich` profiles are submitted
- **THEN** each one's extraction activity is scheduled on the queue derived for
  its own profile, and no two profiles share a queue

#### Scenario: A submission mixes profiles
- **WHEN** one submission carries documents of different processing profiles
- **THEN** the submission is accepted and each document's extraction is routed
  to its own profile's queue

#### Scenario: Validations unrelated to routing still apply
- **WHEN** one submission mixes push and pull documents
- **THEN** it is refused, as it was before extraction could be routed

### Requirement: Everything but extraction stays on the common queue
Knowledge Flow SHALL start every ingestion workflow and sub-workflow on the
configured base task queue, and SHALL run every activity other than the two
extraction activities there, whatever profile the documents carry.

#### Scenario: The pipeline around extraction is unrouted
- **WHEN** a document of any profile is ingested
- **THEN** its root workflow, its per-file sub-workflows, and its metadata,
  progress-event and indexing activities all run on the base task queue

#### Scenario: Non-ingestion work is unaffected
- **WHEN** a corpus re-vectorization, a vector-metadata repair, a fast-vector
  store or delete, or the recurring PDF-render expiry runs
- **THEN** it runs on the base task queue, as it did before extraction could be
  routed

### Requirement: A worker's role decides its queue and its registrations
Knowledge Flow SHALL configure each worker process with the roles it serves. A
worker serving the common role SHALL register every ingestion workflow and every
activity except the two extraction activities, and poll the base task queue. A
worker serving an extraction role SHALL register the two extraction activities,
register no workflow, and poll that profile's derived queue.

#### Scenario: Common role registration
- **WHEN** a worker serves the common role
- **THEN** it polls the base task queue, registers every ingestion workflow, and
  does not register either extraction activity

#### Scenario: Extraction role registration
- **WHEN** a worker serves an extraction role for a profile
- **THEN** it polls that profile's derived queue, registers only the push and
  pull extraction activities, and registers no workflow

#### Scenario: A single process may serve every role
- **WHEN** a worker process is configured with all four roles
- **THEN** it runs one Temporal worker per role and every queue has a consumer

#### Scenario: An unusable role configuration is refused
- **WHEN** the configured role list is empty or names a role twice
- **THEN** configuration loading fails with a message naming the problem, and no
  worker starts on a queue it was not configured for

### Requirement: An unrouted document fails visibly
Knowledge Flow MUST fail a document whose payload carries no extraction queue,
with a terminal error naming the document, rather than scheduling its extraction
on the common queue.

#### Scenario: Extraction queue missing from the payload
- **WHEN** a per-file workflow reaches extraction and its payload carries no
  extraction queue
- **THEN** the document's workflow fails with a non-retryable error naming the
  document, and the document reaches a terminal state

### Requirement: Extraction concurrency is bounded per worker group
Knowledge Flow SHALL make each worker group's activity concurrency
configurable, and its standard deployment SHALL run at most one extraction at a
time on a `rich` pod.

#### Scenario: One rich extraction per pod
- **WHEN** the standard deployment renders the rich extraction worker
- **THEN** that deployment's activity concurrency is one

#### Scenario: Extraction threads fit the CPU budget
- **WHEN** a worker group runs docling extractions
- **THEN** its configured docling thread count multiplied by its activity
  concurrency does not exceed the CPU limit of its pods

### Requirement: The standard deployment consumes every queue it routes to
The Helm chart SHALL provide one worker deployment per role, and the queues
those deployments poll SHALL be the queues the same values route submissions to.
The chart MUST refuse to render when the enabled worker deployments do not cover
the four roles between them, because an activity on a queue nobody polls is never
started and therefore never times out.

#### Scenario: Four worker groups
- **WHEN** the chart renders with the ingestion workers enabled
- **THEN** it produces one deployment for the common role and one for each
  profile's extraction role, each polling the queue derived from the shared base
  task queue

#### Scenario: Only the historical worker is enabled
- **WHEN** a values file enables the common worker deployment alone
- **THEN** the chart refuses to render and names the extraction roles left
  without a consumer

#### Scenario: One deployment serving every role
- **WHEN** a values file enables a single worker deployment configured with all
  four roles
- **THEN** the chart renders, and that deployment polls all four queues

### Requirement: Worker groups share their configuration through render-time inheritance
The Helm chart MUST give the four worker groups one shared source for their
Temporal connection, base task queue, content storage and image, resolved after
values overrides are merged, so that overriding any of them reaches every group.

#### Scenario: Overriding the Temporal server and base queue
- **WHEN** a values file overrides the Temporal host, namespace, base task queue,
  content storage or image of the common worker deployment
- **THEN** the three extraction deployments render with the same overridden
  values, and only their role, concurrency and resources differ

### Requirement: The API and the worker groups render one ingestion configuration
The knowledge-flow API derives each profile's extraction queue name when it
submits and writes the uploaded document to content storage before any worker
reads it, so a rendered deployment MUST show the API and all four worker groups
carrying the same Temporal server, namespace, base task queue, content storage
and document destination. The API SHALL be configured explicitly alongside the
workers; no inheritance makes a worker override reach it.

#### Scenario: A whole ingestion deployment retuned for an environment
- **WHEN** an overlay configures the knowledge-flow API and the common worker with
  the same non-default Temporal server, namespace, base task queue, content
  storage and vector store index, and enables the four worker deployments
- **THEN** the API and the four worker groups render with those same values, while
  each worker group keeps its own role and activity concurrency

#### Scenario: The API is left on other values
- **WHEN** an overlay retunes the workers but leaves the API on different Temporal
  or storage settings
- **THEN** the deployment check reports each setting they disagree on, naming the
  application that diverges

### Requirement: Recurring maintenance stays with the common role
Knowledge Flow SHALL sync the recurring maintenance schedules only from a worker
serving the common role, and those schedules SHALL target the base task queue.

#### Scenario: An extraction worker restarts
- **WHEN** an extraction worker starts or restarts
- **THEN** it posts no schedule, and the PDF-render expiry schedule keeps
  targeting the base task queue

#### Scenario: The schedule survives a common worker restart
- **WHEN** a worker serving the common role starts
- **THEN** the PDF-render expiry schedule is synced against the base task queue,
  and a failure to sync it does not prevent the worker from serving ingestion

### Requirement: Stages exchange work through shared storage only
Knowledge Flow MUST pass extraction's input and output through shared content
storage, and MUST NOT make one stage depend on a temporary file left by the pod
that ran the previous stage, nor carry file content in Temporal payloads.

#### Scenario: Extraction runs on a different pod from metadata
- **WHEN** extraction runs for a push document
- **THEN** it restores its input from content storage rather than from a local
  path produced by an earlier stage

#### Scenario: Indexing runs on a different pod from extraction
- **WHEN** indexing runs after extraction
- **THEN** it restores extraction's output from content storage

### Requirement: A worker's effective configuration is visible at startup
Knowledge Flow SHALL log, when a worker starts, the role it serves, the queue it
polls, its effective activity concurrency, and its workflow-task concurrency
where that is meaningful, without logging secrets or sensitive configuration.

#### Scenario: Reading a running worker's configuration
- **WHEN** a worker process starts
- **THEN** its logs name each role served, the queue polled for it, and the
  activity concurrency applied, and for the common role the workflow-task
  concurrency as well

### Requirement: Documents are admitted per profile without blocking each other
Knowledge Flow SHALL admit the documents of one submission through a bounded
window per processing profile, so that a document of one profile can start while
another profile's window is full. A freed slot MUST be reusable without waiting
for the other documents in flight, and the number of open child workflows MUST
stay within the announced per-profile and total bounds.

#### Scenario: Cheap documents behind expensive ones
- **WHEN** a submission places several `rich` documents before `fast` ones and the
  rich window is full
- **THEN** the `fast` documents are admitted and progress while the rich ones are
  still running

#### Scenario: A freed slot is reused immediately
- **WHEN** one document of a profile finishes while others of that profile are
  still waiting to be admitted
- **THEN** the next document of that profile is admitted without waiting for the
  documents of any other profile

#### Scenario: Bounds are respected
- **WHEN** a submission holds more documents of a profile than that profile's
  window
- **THEN** the number of children open for that profile never exceeds its window,
  and the total never exceeds the sum of the windows of the profiles present

### Requirement: One document's failure does not end the submission
Knowledge Flow MUST contain a document's failure to that document: the other
documents of the submission SHALL keep running and the ones not yet admitted
SHALL still be admitted. The submission's result MUST carry how many documents
succeeded and how many failed, and MUST NOT report success when documents failed.

#### Scenario: A document fails mid-submission
- **WHEN** one document of a submission fails permanently
- **THEN** its own task reaches a terminal failed state, the other documents run
  to completion, and the submission's result reports one failure

#### Scenario: Cancellation is not a failure
- **WHEN** a submission is cancelled
- **THEN** no further document is admitted, and the outcome is reported as
  cancelled rather than as a document failure

#### Scenario: The submission itself is cancelled while documents are running
- **WHEN** the cancellation reaches the parent workflow while it is waiting on
  the documents it has admitted, rather than being reported by one of them
- **THEN** no further document is admitted, the documents already running are
  cancelled, and their outcomes are all collected before the cancellation
  propagates

#### Scenario: A terminal event that could not be persisted
- **WHEN** a document's terminal event cannot be written after its bounded retries
- **THEN** the document's task is left non-terminal and the existing reconciliation
  drives it to a terminal state from the submission's executor status

### Requirement: Execution budgets exclude queue waiting
Knowledge Flow SHALL bound each ingestion activity by a per-attempt execution
budget that does not include the time the activity waits in its queue, and SHALL
bound the number of attempts per activity according to its nature.

#### Scenario: A saturated queue does not consume the execution budget
- **WHEN** an activity waits in its task queue longer than its execution budget
  before a worker starts it
- **THEN** the activity still receives its full execution budget once started

#### Scenario: A permanent error is not retried
- **WHEN** an activity fails with an error that retrying cannot resolve
- **THEN** the attempt is not retried and the document reaches a terminal state

#### Scenario: A missing input is told apart from a storage outage
- **WHEN** an extraction cannot restore its input
- **THEN** a genuinely absent input fails permanently while a transient storage
  failure remains retryable

### Requirement: Cancelling an extraction stops the computation
Knowledge Flow MUST run each extraction in a child process it can terminate, and
MUST NOT release the extraction's worker slot, remove its working directory, or
report the activity finished until that process and its process group have been
terminated and reaped.

#### Scenario: Cancelling a running extraction
- **WHEN** a running extraction is cancelled
- **THEN** its child process and any descendant it started are terminated, their
  termination is confirmed, and only then does the activity finish

#### Scenario: A new extraction does not overlap an abandoned one
- **WHEN** an extraction is cancelled and another is admitted on the same worker
- **THEN** the new extraction starts only after the previous computation has
  actually stopped

#### Scenario: The local budget expires
- **WHEN** an extraction exceeds the budget the activity derived for it
- **THEN** the activity terminates the child process itself rather than relying on
  the executor's timeout, and reports a timeout

#### Scenario: The attempt has no budget left to give
- **WHEN** the time left on an attempt, once the shutdown reserve is kept, is
  zero or less
- **THEN** the activity fails the attempt before creating a child process, rather
  than starting an extraction it could only terminate part-way through

#### Scenario: Cancellation during process start-up
- **WHEN** an extraction is cancelled before its child process is fully installed
- **THEN** no child process is left running

#### Scenario: A second cancellation during the stop
- **WHEN** the activity is cancelled again while it is already terminating its
  child process
- **THEN** the termination is carried through to the end rather than abandoned or
  left to finish in the background, and the event loop stays responsive
  throughout

#### Scenario: The child ends by itself leaving a descendant
- **WHEN** the child process finishes on its own, with a success or with an
  error, having started a descendant that is still running
- **THEN** that descendant is terminated too before the activity finishes

#### Scenario: The termination cannot be confirmed
- **WHEN** the child process, or something in its process group, is still alive
  after the termination timeout
- **THEN** the activity fails with an error that says the stop was not confirmed,
  in place of the success, timeout or cancellation it was about to report, so
  that no outcome states the worker is free for the next extraction

#### Scenario: The worker is killed outright
- **WHEN** the worker process is killed without running its shutdown path
- **THEN** the extraction child process does not survive it

#### Scenario: The child's parent died before the death signal was installed
- **WHEN** the child process finds, at start-up, that its parent is not the
  worker that started it
- **THEN** it exits instead of running the extraction, whatever pid it has been
  re-parented to

### Requirement: The outcome of a killed extraction keeps its nature
Knowledge Flow SHALL distinguish a permanent document error, a transient failure,
a budget timeout, a cancellation and an abnormal process exit when extraction runs
in a child process, and MUST NOT collapse them into one retryable failure.

#### Scenario: A permanent error inside the child
- **WHEN** the extraction fails inside the child with an error retrying cannot fix
- **THEN** the activity reports it as permanent and it is not retried

#### Scenario: The child dies abnormally
- **WHEN** the child process is killed by the operating system rather than failing
  in Python
- **THEN** the activity reports an abnormal termination, distinct from a document
  error and from a cancellation
