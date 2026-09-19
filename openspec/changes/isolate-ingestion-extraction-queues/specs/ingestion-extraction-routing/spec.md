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
