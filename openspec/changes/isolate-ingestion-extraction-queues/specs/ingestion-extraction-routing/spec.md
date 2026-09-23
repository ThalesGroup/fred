## Purpose
Define testable ingestion isolation and execution guarantees. Explanations and current limitations: [INGESTION.md](../../../../../docs/swift/design/INGESTION.md).

## ADDED Requirements

### Requirement: Profile routing and common orchestration
The system SHALL derive distinct fast/medium/rich extraction queues from the shared base queue. All workflows and non-extraction activities SHALL stay common.
#### Scenario: Mixed profiles
- **WHEN** documents of different profiles are submitted together
- **THEN** the submission is accepted, each extraction uses its profile queue, and metadata/progress/indexing remain common; mixed push/pull submissions remain rejected.

### Requirement: Explicit worker roles
Common SHALL register all workflows and non-extraction activities; extraction roles SHALL register only push/pull extraction and no workflows. Multiple roles per process SHALL be supported; empty or duplicate roles SHALL be rejected.
#### Scenario: Developer and separated workers
- **WHEN** all roles are configured in one process or across separate processes
- **THEN** each role polls its derived queue and logs its role, queue and effective concurrency; recurring maintenance schedules are managed only by common.

### Requirement: Missing routing fails visibly
A missing extraction queue SHALL produce a non-retryable document error, never common-queue extraction.
#### Scenario: Unrouted document
- **WHEN** extraction receives a payload without its queue
- **THEN** the error identifies the document and its task eventually becomes terminal.

### Requirement: Coherent deployment and bounded concurrency
The standard chart SHALL provide four independently configurable role deployments, one rich extraction per pod, render-time inheritance and complete role coverage. API and workers SHALL agree on Temporal, queues and shared storage; extraction threads multiplied by activity concurrency SHALL fit the configured CPU limit.
#### Scenario: Configuration override
- **WHEN** shared worker values are overridden and the API is configured to match
- **THEN** all extraction deployments inherit those values while retaining role-specific capacity; a render leaving any role unserved is rejected, while one all-role worker is accepted.

### Requirement: Shared stage handoff
Stages SHALL exchange document data through shared storage, not Temporal payload bytes or another worker's temporary paths.
#### Scenario: Different workers
- **WHEN** extraction and indexing run on different workers
- **THEN** each restores the required input and indexing consumes the persisted extraction output.

### Requirement: Independent bounded admission
Admission SHALL be bounded per normalized extraction profile per submission, with total admission bounded by the sum of present profile windows.
#### Scenario: Rich window full
- **WHEN** rich documents occupy their admission window
- **THEN** eligible fast/medium documents start and freed slots are reused without waiting for other profiles.

### Requirement: Document outcomes and cancellation remain distinct
A document failure SHALL not stop siblings. The parent SHALL report totals/failures, cancellation SHALL stop admission and cancel/collect running children, and task reconciliation SHALL recover missing terminal events.
#### Scenario: Partial failure or cancellation
- **WHEN** a document fails or cancellation reaches either a child or the waiting parent
- **THEN** failure permits remaining documents to finish with accurate outcomes, whereas cancellation drains running children before propagating; lost terminal events eventually yield terminal tasks.

### Requirement: Execution budgets and error classification
Activities SHALL have per-attempt execution budgets excluding queue wait and bounded retries. Permanent document/missing-input errors, transient storage failures, timeouts, cancellation and abnormal child exits SHALL remain distinguishable.
#### Scenario: Waiting and retrying
- **WHEN** an activity starts after a long queue wait or an attempt fails
- **THEN** it receives its full execution budget; permanent errors are not retried, transient failures remain retryable, and an OS-killed child is not classified as a permanent document error.

### Requirement: Extraction termination controls capacity
Extraction SHALL run in a terminable child process; its computation and descendants MUST stop before releasing capacity or deleting working files. Unconfirmed termination MUST override any normal outcome with an explicit error and MUST NOT permit overlapping extraction work.
#### Scenario: Cancellation, deadline or orphan cleanup
- **WHEN** cancellation occurs during startup/execution/cleanup, the local budget expires, or a child exits leaving descendants
- **THEN** cleanup finishes without blocking the event loop or abandoning descendants; repeated cancellation does not interrupt it, and a depleted budget starts no child.
#### Scenario: Worker loss
- **WHEN** a worker dies, including before the child's parent-death guard is installed
- **THEN** its extraction child does not survive; a child detecting a different parent refuses to run.
