## MODIFIED Requirements

### Requirement: The existing document UI remains the product surface

The Resources routes, navigation, pages, controls and styles SHALL be preserved.
Their data bindings SHALL use manager folder/document identities without treating
them as knowledge-flow tags. The upload drawer, import panel, metadata rows,
statistics/quota and download action SHALL agree on the stored-original outcome.
Upload-only SHALL remain available without ingestion services. Upload-and-process
SHALL let the user select an existing processing profile and follow processing
through manager. A stored original SHALL NOT imply completed processing or
availability in search/chat. Completed derived outputs SHALL be accessible through
the existing authorized preview surface where that file type supports preview.

#### Scenario: Processing services are unavailable
- **WHEN** Temporal and ingestion services are unavailable
- **THEN** an authorized user can import an original, leave and return to Resources, reload and download it
- **AND** existing folder navigation/create/rename/delete behavior remains available subject to document protection
- **AND** an accepted processing request remains visible with a durable pending or failure outcome rather than false success

#### Scenario: Account changes while receipts are cached
- **WHEN** the browser changes authenticated user or organization context
- **THEN** the new context does not display or retry the previous actor's cached imports

#### Scenario: A document completes processing
- **WHEN** the user imports with processing and later reloads the folder and import panel
- **THEN** both surfaces agree on the persisted stage and terminal outcome for the same document
- **AND** the original remains downloadable and published preview is shown without exposing credentials or unsafe active content

#### Scenario: PDF and Office native previews work without the Knowledge Flow HTTP API
- **WHEN** a supported PDF or Office document has completed processing and the Knowledge Flow HTTP API is stopped
- **THEN** the existing File and Raw modes load the correct native PDF and extracted preview through manager with current authorization
- **AND** neither the default File mode nor range loading depends on the old API

## ADDED Requirements

### Requirement: Processing acceptance is durable and separate from original storage

Manager SHALL accept an explicit processing profile with an upload, or a later
processing request for a stored-only or failed document. Upload publication and
its requested processing intent SHALL be committed together. Idempotency SHALL
bind the actor's request key to the document input, destination and processing
choice. At most one processing attempt per document SHALL be active. Processing
failure SHALL preserve the original, placement, identity and original quota charge.

#### Scenario: The upload response is lost
- **WHEN** upload-and-process commits and its response is lost
- **THEN** receipt recovery or identical replay returns the same original and processing attempt
- **AND** there is no additional upload, processing admission or quota charge

#### Scenario: A processing choice changes under one key
- **WHEN** a request key is replayed with another processing mode or profile
- **THEN** manager reports an idempotency conflict and does not start another operation

#### Scenario: Concurrent starts or retries
- **WHEN** editors concurrently start processing or retry the same failed attempt
- **THEN** at most one successor is admitted and matching requests can resolve its identity
- **AND** conflicting choices receive an explicit conflict

#### Scenario: Processing is retried after failure
- **WHEN** a currently authorized editor retries a failed processing attempt
- **THEN** processing uses the existing immutable original and records a distinct linked attempt
- **AND** the client does not need to select or resend the original file

### Requirement: Manager dispatches processing directly through Temporal

Accepted manager work SHALL be delivered to the Knowledge Flow worker through
Temporal without calling its HTTP ingestion API. Delivery SHALL survive manager
restarts and uncertain acknowledgments with the same operation identity. Workflow
history SHALL carry bounded references and orchestration data, never document
bytes, extracted text, embedding arrays or bearer/storage credentials. Unsupported
contract versions SHALL fail explicitly before processing effects.

#### Scenario: The Knowledge Flow HTTP API is stopped
- **WHEN** manager, Temporal and the required Knowledge Flow workers are available and a supported document is imported with processing
- **THEN** its extraction and output processing complete without any request to the Knowledge Flow HTTP API

#### Scenario: A start acknowledgment is lost
- **WHEN** Temporal accepts a workflow and manager loses the response or restarts
- **THEN** recovery resolves that execution and cannot create another execution, even if the original completed

#### Scenario: A dependency or consumer is absent
- **WHEN** Temporal is unavailable or the required worker queue has no consumer
- **THEN** original storage remains usable and accepted work retains its identity and visible state
- **AND** configured retry/queue/execution bounds eventually produce an actionable outcome or recovered execution

#### Scenario: Execution history is no longer available
- **WHEN** an old ambiguous delivery cannot be resolved from retained execution history
- **THEN** the system preserves its receipt and reports the ambiguity without guessing success or starting duplicate work

### Requirement: Worker execution is authorized by manager-owned scope

Only an authenticated allowed worker workload SHALL access the worker protocol.
Manager SHALL bind every operation to its accepted document, installation, owning
space, original digest and current attempt. Original access and successful result
publication SHALL enforce the initiating actor's current admission and effective
Write authority. Public processing/status/preview routes SHALL use the current
caller and the existing owning-space policy. Worker identity, platform roles,
serialized user claims and submitted IDs SHALL NOT substitute for this authority.
No legacy folder/document grants or catalog entries SHALL be created.

#### Scenario: Human or foreign workload targets the worker route
- **WHEN** a human token, wrong audience/issuer/client, or mismatched operation identity calls a worker route
- **THEN** access is refused without returning original bytes or accepting result publication

#### Scenario: Access changes while work is queued or running
- **WHEN** the initiating actor loses admission or Write authority before original access or final publication
- **THEN** that boundary refuses the operation and no new processed result is published
- **AND** the failure can still be persisted, while the original remains accessible only to current authorized readers

#### Scenario: Scope and content roles differ
- **WHEN** a member, editor, analyst, administrator, owner or platform user starts processing or reads its result in personal, organization, team or project scope
- **THEN** the current manager permission model determines access, including inherited roles and project isolation
- **AND** an administrative role alone cannot process or read content

### Requirement: Processing reuses configured pipelines and publishes isolated results

Manager SHALL submit the existing ProcessPush workflow using the unchanged
PipelineDefinition/FileToProcess contract and Python-owned submission policy.
The existing workflows, activity signatures and configured pipeline routing SHALL
be reused through explicit storage/authority adapters, without a parallel ingestion
pipeline. Knowledge Flow workers SHALL apply the selected profile's configured extraction
and output behavior, including text chunks/embeddings or the existing tabular
pipeline as appropriate. Manager document identity and immutable owning scope
SHALL be preserved in all derived artifacts and index records. Manager results
SHALL be isolated from legacy catalog, retrieval, expiry and repair paths.
Success SHALL require verified durable output and its accepted publication, not
merely completion of extraction or workflow orchestration.

#### Scenario: Text or tabular processing succeeds
- **WHEN** supported text/PDF and tabular fixtures run through their configured profiles
- **THEN** text has persisted chunks and embeddings and tabular content has its configured durable output
- **AND** manager records the matching manifest and counts with the original document identity

#### Scenario: One profile is busy
- **WHEN** rich extraction is occupied and fast/medium work is accepted
- **THEN** the existing independent extraction queues and configured concurrency remain effective
- **AND** indexing executes on the common worker role

#### Scenario: Unsupported input or output dependency failure
- **WHEN** the file/profile cannot be processed or storage/model/index work exhausts its retry policy
- **THEN** processing reports a safe failure identifying the stage and the original remains downloadable
- **AND** partial output cannot appear as a published successful result

#### Scenario: Office native render cannot be produced
- **WHEN** native PDF conversion for a supported Office format exhausts its processing retry policy
- **THEN** the manager attempt fails with a safe preview-stage error rather than publishing success with a broken default preview
- **AND** the original remains downloadable and a current editor can retry processing without another upload

#### Scenario: A legacy consumer enumerates its data
- **WHEN** legacy Knowledge Flow search, document listing, preview, expiry or repair runs
- **THEN** it cannot return, expose or mutate manager-owned processing artifacts or index records

### Requirement: Retries and stale workers cannot corrupt published results

Processing stage transitions and result publication SHALL be idempotent, ordered
and fenced against obsolete executions. Duplicate or delayed callbacks SHALL NOT
regress progress, replace a terminal result, mix generations or publish stale
output. Cleanup SHALL eventually remove abandoned partial results, including
late writes, while protecting original content and published results. Processing
admission, temporary/derived storage, work concurrency and cleanup SHALL have
explicit bounded capacity and backpressure.

#### Scenario: A timed-out worker writes after its replacement
- **WHEN** an old activity resumes while a replacement has claimed or committed the stage
- **THEN** old writes remain unpublished and cannot overwrite, delete or mix with the replacement's results
- **AND** cleanup eventually removes only the abandoned generation

#### Scenario: Publication acknowledgment or progress arrives late
- **WHEN** publication succeeds but its response is lost, or an earlier progress/failure update arrives afterward
- **THEN** replay returns the committed result and the visible terminal outcome remains unchanged

#### Scenario: Manager restarts during final publication
- **WHEN** durable output exists but manager fails around the final commit
- **THEN** recovery resolves the same manifest to committed success or retained failure/pending work
- **AND** no success is invented from workflow completion alone

#### Scenario: Capacity is exhausted or cleanup loses authority
- **WHEN** a configured work/storage budget is exhausted or authoritative state cannot be checked
- **THEN** new work is bounded or refused with a safe outcome, and destructive cleanup waits for authoritative state
- **AND** published results and original documents remain protected

### Requirement: Processing state is recoverable and observable

Manager SHALL retain authoritative stage/status, attempt identity, timestamps,
result summary and safe failure codes. Existing UI surfaces SHALL rehydrate this
state without one authorization decision per document or chunk. Acknowledgment
of upload completion SHALL NOT hide active processing. Logs SHALL correlate work
without leaking tokens, content or provider diagnostics to user responses. The
deployed configuration SHALL explicitly bind manager and workers to matching
Temporal, workload authentication and isolated storage settings.

#### Scenario: Reload or lost polling response
- **WHEN** the browser reloads, reconnects or misses intermediate updates
- **THEN** it recovers the current stage and final outcome from manager without replaying effects or inventing progress percentages

#### Scenario: Directory size grows
- **WHEN** the same user reads one bounded page or processing summary with 1 or 100 stored documents
- **THEN** authorization work depends on owning-space context rather than document/chunk cardinality
- **AND** measured RPC counts, pagination and lock duration are recorded with fixture size and concurrency

#### Scenario: Invalid deployment bindings
- **WHEN** processing configuration is incomplete, mixes manager results with legacy stores, or provides an unsupported worker contract
- **THEN** startup or processing admission fails with an actionable safe diagnostic rather than routing to another authority
