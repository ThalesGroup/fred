## Purpose

Let an authorized user store an original document in its owning space, find its
metadata and download the same bytes, with reliable admission and recovery.

## ADDED Requirements

### Requirement: Storage is authorized by the owning space

Manager SHALL require current admission, a valid organization context and the
owning space's effective Write permission for upload, and Read permission for
metadata, listing, receipts and original download. Publication SHALL revalidate
the writer after transfer. OpenFGA SHALL remain canonical for roles and hierarchy;
folders and documents SHALL NOT acquire independent grants.

#### Scenario: Effective content roles and administrative roles differ
- **WHEN** users with direct/inherited editor, analyst, member, admin, owner and platform roles exercise the document routes
- **THEN** the implemented space permission model determines each result
- **AND** administration alone does not grant content access and personal ownership does not widen another space's access

#### Scenario: Access changes during upload
- **WHEN** access or admission is revoked before the publication transaction is authorized
- **THEN** no document is published and the pending bytes become eligible for cleanup

#### Scenario: A caller supplies a foreign identifier
- **WHEN** a caller targets another organization's folder, document or receipt
- **THEN** the request reveals neither metadata nor content and performs no mutation

### Requirement: A stored original is a durable document

A successful upload SHALL publish one document in one named folder and one
immutable owning space, with a stable UUID, canonical name, MIME metadata, actual
byte length, server-computed SHA-256, creator and creation time. Success SHALL mean
that durable original bytes match that metadata. Pending or failed uploads SHALL
NOT appear as stored documents. Root-level uploads SHALL be refused.

#### Scenario: Import, reload and download
- **WHEN** an editor imports a file, reloads Resources and opens its folder
- **THEN** the document appears exactly once with correct metadata
- **AND** its download has the same byte length and SHA-256 as the selected file

#### Scenario: Storage write fails
- **WHEN** original storage or integrity verification fails
- **THEN** no successful document result is returned and no ready metadata row is exposed

### Requirement: Upload requests are idempotent and create only

An upload SHALL have an actor-scoped idempotency key bound to its target, name and
verified content. An identical completed replay SHALL return the same document;
different content or placement with that key SHALL return a conflict. Concurrent
uploads of the same canonical name to the same folder SHALL publish at most one
document. Existing content SHALL never be overwritten by this workflow.

#### Scenario: The success response is lost
- **WHEN** the server commits an upload and the client loses its response
- **THEN** receipt lookup or an identical replay returns the original document ID without duplicate storage or quota charge

#### Scenario: Two requests race for a name
- **WHEN** different request keys upload the same name into one folder concurrently
- **THEN** at most one succeeds and the other receives an explicit name conflict
- **AND** the same name remains valid in a different folder

#### Scenario: A key is misused or still active
- **WHEN** a key is reused for different bytes or a concurrent attempt is still running
- **THEN** the API distinguishes key conflict from upload-in-progress and provides a safe retry/receipt outcome

#### Scenario: Retry and dismissal survive browser state loss
- **WHEN** a failed upload is successfully retried or its terminal entry is dismissed, then the user returns with cleared browser data
- **THEN** the resolved predecessor is not reintroduced as an unresolved failure
- **AND** acknowledgment preserves the original idempotency outcome and does not delete stored content

#### Scenario: Two clients retry the same failure
- **WHEN** two clients retry one failed receipt concurrently with different request keys
- **THEN** at most one successor reservation is created and both clients can resolve its outcome

### Requirement: Storage limits are enforced at admission

The service SHALL enforce configured file, request, concurrency, temporary-storage,
duration and quota limits using actual received bytes. Quota admission SHALL count
committed bytes and concurrent reservations. Projects SHALL charge their canonical
parent team once; personal and organization-owned content SHALL use their own
configured budgets. Preflight SHALL be advisory and SHALL NOT reserve capacity.

#### Scenario: Concurrent requests approach a shared quota
- **WHEN** concurrent uploads to a team and its projects would together exceed the budget
- **THEN** only requests fitting the serialized reservation budget are admitted
- **AND** retries do not double-charge and a personal space's budget is unaffected

#### Scenario: A caller understates size or exhausts capacity
- **WHEN** a body exceeds the limit, stalls, or no transfer capacity remains
- **THEN** the request terminates with a documented bounded failure, without unbounded buffering or queuing

#### Scenario: Cleanup cannot keep pace
- **WHEN** uncollected failed objects exceed the configured cleanup backlog budget
- **THEN** new upload admission stops and operators can identify the storage failure

### Requirement: Interrupted uploads cannot corrupt lifecycle state

After process failure or an ambiguous remote write, the system SHALL retain a
durable recoverable outcome, prevent late publication by abandoned attempts and
eventually remove unpublished objects when dependencies recover. This SHALL work
without Temporal or knowledge-flow. Cleanup SHALL NOT remove published originals.
Pending reservations and stored documents SHALL protect their folder subtree and
owning space from deletion.

#### Scenario: Crash at a transfer boundary
- **WHEN** a process dies after reservation, after remote write, or after publication but before responding
- **THEN** restart/reconciliation and receipt lookup distinguish interrupted operations from committed documents
- **AND** retry cannot create a second committed document for the same successful request

#### Scenario: A remote write completes after cleanup
- **WHEN** a timed-out write becomes visible after an earlier cleanup attempt
- **THEN** recurring reconciliation eventually removes it and it never becomes a published document

#### Scenario: Folder or space deletion races upload
- **WHEN** deletion races reservation, publication or abandonment
- **THEN** either the upload protects an active target or deletion wins and upload fails
- **AND** neither path recreates a deleted target or removes a stored original

### Requirement: Browsing and download expose current authorized data

Resources SHALL present folders and stored documents through one consistently
filtered and sorted bounded page with a coherent total and stable tie-breaks.
Metadata/detail/download SHALL authorize the current owning space. Original
downloads SHALL stream from manager as safe attachments without a public storage
URL or whole-file buffering on the server. The browser SHALL bound individual
download size and concurrency; bulk and recursive downloads SHALL remain visibly
unavailable in this slice. Missing/corrupt content SHALL NOT be returned as an
empty success.

#### Scenario: Mixed directory pagination
- **WHEN** a directory has more folders and documents than fit on a page
- **THEN** sorting, filtering, total and navigation describe the same directory snapshot for each request
- **AND** independent folder/document pages are not merged into a misleading result

#### Scenario: Access is revoked before download
- **WHEN** the user requests content after Read permission has been revoked
- **THEN** no bytes or reusable storage capability are returned

#### Scenario: An unsafe name or incomplete stream is encountered
- **WHEN** a filename could alter paths/headers, or the storage stream fails
- **THEN** unsafe upload names are refused, download headers remain safe, and a failed stream cannot appear as a complete file

#### Scenario: A download could exceed browser limits
- **WHEN** a document exceeds the published individual-download limit or a download is already active
- **THEN** the browser does not start another unbounded Blob transfer
- **AND** selecting a folder or multiple files cannot trigger the legacy unbounded ZIP path

### Requirement: The existing document UI remains the product surface

The Resources routes, navigation, pages, controls and styles SHALL be preserved.
Their data bindings SHALL use manager folder/document identities without treating
them as knowledge-flow tags. The upload drawer, import panel, metadata rows,
statistics/quota and download action SHALL agree on the stored-original outcome.
This journey SHALL make no ingestion or Temporal call and SHALL not claim that
stored originals are indexed, searchable or processed.

#### Scenario: Processing services are unavailable
- **WHEN** Temporal and ingestion services are unavailable
- **THEN** an authorized user can import an original, leave and return to Resources, reload and download it
- **AND** existing folder navigation/create/rename/delete behavior remains available subject to document protection

#### Scenario: Account changes while receipts are cached
- **WHEN** the browser changes authenticated user or organization context
- **THEN** the new context does not display or retry the previous actor's cached imports

### Requirement: Storage contracts are observable and configured explicitly

The deployed manager SHALL validate typed content-store and transfer configuration,
emit safe structured outcomes for upload/retry/cleanup, and provide documented
machine-readable failure codes. Logs and API errors SHALL omit credentials,
bearer tokens, file contents, SQL internals and provider diagnostics. Authorization
request budgets SHALL be measured independently of document count.

#### Scenario: Invalid deployment configuration
- **WHEN** a required storage setting is absent or limits are inconsistent
- **THEN** startup/admission fails with an actionable safe diagnostic instead of silently using an unrelated Python store

#### Scenario: Provider outage and recovery
- **WHEN** the object store fails and later recovers
- **THEN** users receive a retryable dependency outcome and operators can see the unresolved cleanup backlog and its recovery
