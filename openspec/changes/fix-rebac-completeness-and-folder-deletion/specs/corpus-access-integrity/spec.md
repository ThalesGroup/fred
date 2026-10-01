## Purpose

Define the agreed team-scoped document corpus behavior, explicit admission conflicts and asynchronous deletion without application-level infrastructure fallback mechanisms.

## ADDED Requirements

### Requirement: Team-scoped corpus permissions

All team members SHALL be able to read the team's corpus. Only team editors SHALL mutate it. The owner of a personal team SHALL manage their own corpus. Corpus folders and documents SHALL NOT have separate human sharing grants. A synchronization source account SHALL retain access limited to its assigned root folder and descendants, checked at operation admission without per-document grants. Public team-profile visibility alone MUST NOT authorize corpus access.

#### Scenario: Reader and editor
- **WHEN** a team member without editing rights reads and then attempts to change a document
- **THEN** reading succeeds and mutation is refused

#### Scenario: Personal corpus
- **WHEN** a user accesses their own personal-team corpus
- **THEN** they can read and manage it without access to another user's personal corpus

#### Scenario: Source account is restricted to its synchronization tree
- **WHEN** a source account writes inside its assigned synchronization root or its descendants
- **THEN** its root grant is checked at admission without document-level grants
- **AND** that grant does not authorize another folder of the same team

### Requirement: Explicit single-folder corpus membership

Each corpus document SHALL belong to exactly one folder. A folder and its descendants SHALL belong to one team and inherit that team's permissions for human access. The user SHALL create or select a folder before corpus ingestion; Fred MUST NOT automatically create a default folder. Moves SHALL remain within the same team. Conversation attachments SHALL remain associated with their conversation, logically separated and absent from the corpus. The shared metadata table SHALL distinguish corpus and attachment rows explicitly and enforce their respective folder requirements. Descriptive labels SHALL NOT grant access.

#### Scenario: Missing destination
- **WHEN** corpus ingestion is requested without a folder
- **THEN** the request is refused instead of creating a default folder

#### Scenario: Cross-team move
- **WHEN** a move targets another team
- **THEN** it is refused

#### Scenario: Move during ingestion
- **WHEN** an existing membership-changing operation, such as source synchronization, requests another folder for a document with active ingestion
- **THEN** the move is refused without changing its destination
- **AND** the change can be requested again once ingestion has finished
- **AND** this rule does not require a new document-move UI or API

#### Scenario: Conversation attachment
- **WHEN** a file is attached to a conversation
- **THEN** it stays outside the corpus and requires no corpus-folder creation

### Requirement: Corpus inventory independent of authorization enumeration limits

Authorized corpus listings, totals and deletion inventories SHALL be complete within their requested scope regardless of unrelated corpus size or FGA document enumeration limits. Requested identifiers MUST belong to the stored authorized scope. Pagination SHALL NOT lose authorized results through filtering an incorrectly scoped page.

#### Scenario: Large corpus
- **WHEN** an authorized user opens a folder of 20 documents in a team with more than 1,000 documents
- **THEN** its 20 documents and correct total are returned through normal pagination

#### Scenario: Foreign identifier
- **WHEN** a request supplies an authorized team ID with a document from another team
- **THEN** the authorized team ID does not grant access to that document

### Requirement: Conflict rejection before subtree deletion

Deleting a folder SHALL delete its descendants and documents after explicit UI confirmation. Deletion SHALL be refused while ingestion is active in the subtree; Fred SHALL NOT cancel ingestion or queue deletion to wait for it. Accepted deletion SHALL hide the tree from navigation and reject new additions or moves into it.

#### Scenario: Active ingestion
- **WHEN** deletion targets a subtree with active ingestion
- **THEN** knowledge-flow backend refuses deletion before requesting a Temporal workflow and the user can request it after ingestion finishes

#### Scenario: Ingestion starts after deletion preflight
- **WHEN** no ingestion was active at the knowledge-flow backend preflight but one is active when the Temporal deletion execution attempts its final claim
- **THEN** the deletion reports a conflict without deleting any document and does not cancel or wait for that ingestion

#### Scenario: Write into deleting tree
- **WHEN** a new addition targets an accepted deletion's subtree
- **THEN** the addition is refused

### Requirement: Native asynchronous deletion execution

Accepted deletion SHALL run through Temporal and resume after worker restart using Temporal's execution contract. Failure SHALL remain visible and SHALL NOT restore a partially deleted tree. Successful cleanup SHALL remove deleted corpus data and temporary cleanup records from PostgreSQL and the required external stores. Fred SHALL NOT add a fallback execution queue or compensation sweeper. Submitted corpus deletion SHALL NOT be cancellable through the UI or task API.

#### Scenario: Cancellation of submitted deletion
- **WHEN** a caller requests cancellation of a corpus deletion task
- **THEN** the API refuses with HTTP 409 without cancelling Temporal or scheduling cancellation reconciliation
- **AND** the UI offers no deletion cancellation action

#### Scenario: Worker restart
- **WHEN** a worker restarts during an accepted deletion
- **THEN** Temporal resumes that execution and Fred does not create a parallel recovery job

#### Scenario: Cleanup incomplete
- **WHEN** cleanup has not completed successfully
- **THEN** the tree remains hidden and the task is not reported successful

### Requirement: Accepted search consistency window

Search SHALL be permitted to return document excerpts while deletion cleanup is in progress, including searches started after the deletion request. Once cleanup completes, new searches SHALL no longer retrieve those excerpts. A response already in progress SHALL be permitted to use excerpts obtained earlier.

#### Scenario: Search during cleanup
- **WHEN** a new search runs before deletion cleanup completes
- **THEN** finding an excerpt of the deleting document is an accepted outcome

### Requirement: Authorization at long-running operation admission

Ingestion and deletion SHALL check the required team permission at admission. An accepted operation SHALL finish even if the initiating user subsequently loses that role; it SHALL NOT repeat that authorization for every document or processing step.

#### Scenario: Editor role revoked
- **WHEN** an editor loses the role after a batch or deletion is accepted
- **THEN** the accepted operation continues and new unauthorized operations are refused

### Requirement: Explicit component errors without fallback

New requests requiring unavailable authorization SHALL fail explicitly without fallback permissions. A scheduler-start error SHALL reach the UI rather than being reported as successful scheduling. Fred SHALL NOT persist ingestion payloads for automatic redelivery. Already accepted Temporal executions SHALL remain Temporal's responsibility.

#### Scenario: Initial scheduler connection failure
- **WHEN** Fred cannot establish its initial connection to Temporal
- **THEN** submission fails explicitly before document task admission and no fallback submission is queued

#### Scenario: Authorization unavailable
- **WHEN** a new corpus request cannot obtain its required authorization decision
- **THEN** it fails explicitly without using a rescue permission source

After an unconfirmed scheduler-start RPC error, knowledge-flow SHALL report the error and retain existing document reservations. It SHALL NOT infer that execution does not exist, automatically redeliver the request or automatically release those reservations. Manual diagnosis and resolution when no execution exists are an accepted limitation.

#### Scenario: Connection breaks before start acknowledgement
- **WHEN** the Temporal client returns a communication error after submitting an ingestion batch and execution existence is unconfirmed
- **THEN** the UI receives an explicit submission error and the document reservations remain
- **AND** if no workflow exists, an operator must diagnose and resolve the reservations before the documents can be admitted again

### Requirement: Nonblocking service waits without inferred business failure

Knowledge-flow backend SHALL await scheduler client results asynchronously without holding its admission SQL transaction during that wait. Configured technical client deadlines SHALL be permitted, but elapsed time or a transport error MUST NOT be interpreted as proof of workflow failure. Fred MUST NOT add a second business timer to manufacture a terminal execution state.

#### Scenario: Slow scheduler response
- **WHEN** a scheduler response takes longer while the client call remains pending
- **THEN** the admission transaction is not kept open and the backend does not declare the workflow failed merely because time has elapsed

#### Scenario: Client deadline expires
- **WHEN** the scheduler client reports a deadline error
- **THEN** the backend reports the communication error without asserting that the workflow failed or never existed

### Requirement: Retire the obsolete knowledge-flow resource surface

The older knowledge-flow resource CRUD API for prompts, templates and chat contexts and its `mcp-resources` exposure SHALL be removed. The current control-plane prompt library SHALL remain available with its existing behavior. Conversation attachments SHALL remain separate and unaffected. Removal MUST NOT silently convert legacy resources into control-plane prompts.

#### Scenario: Current prompt library
- **WHEN** a user lists, edits or uses a prompt through the current control-plane prompt APIs
- **THEN** retirement of the older knowledge-flow resource API does not change that behavior

#### Scenario: Obsolete resource endpoint
- **WHEN** a client calls a removed knowledge-flow resource route after the retirement
- **THEN** it is no longer available and no compatibility forwarding to the control-plane prompt API is introduced

#### Scenario: Legacy data remains at upgrade
- **WHEN** the retirement migration finds legacy resources or non-document folders whose disposition has not been explicitly decided
- **THEN** it stops with actionable instructions rather than silently deleting or converting those data

#### Scenario: Operator migration guidance
- **WHEN** an operator prepares the upgrade
- **THEN** the guide identifies inventory checks, data-decision prerequisites, writer shutdown, schema/configuration changes, verification and rollback limitations


### Requirement: Retire unused direct report creation

The legacy knowledge-flow `/mcp/reports/write` API and `mcp-reports` mount SHALL be removed with their dedicated service, renderer and configuration flag. Existing report documents SHALL NOT be deleted by this retirement. Generic corpus content access and current control-plane prompts SHALL remain available. No replacement report-specific admission or recovery mechanism SHALL be introduced.

#### Scenario: Removed report writer
- **WHEN** a client calls the retired report creation endpoint
- **THEN** the endpoint is unavailable and no direct corpus write occurs

#### Scenario: Historical report document
- **WHEN** a report document already exists
- **THEN** retirement does not purge its files or metadata
- **AND** any missing stored folder remains an explicit single-folder migration review case

### Requirement: Verified historical folder ownership conversion

Migration SHALL convert a historical user-owned folder to that user’s canonical personal team only when PostgreSQL and exactly one explicit ReBAC owner agree. Existing team ownership SHALL be retained. Missing, multiple or inconsistent ownership SHALL stop conversion and identify the affected folders before any owner is changed. This conversion SHALL NOT introduce runtime ownership inference or repair.

#### Scenario: Verified personal owner
- **WHEN** a folder has Alice as its unique explicit ReBAC owner and both SQL and stored JSON identify Alice
- **THEN** migration assigns Alice’s canonical personal team

#### Scenario: Ambiguous owner
- **WHEN** any folder lacks an owner, has multiple owners or disagrees between stores
- **THEN** migration reports the affected folders and changes no folder owner

### Requirement: Service identities have explicit corpus rights
The knowledge-flow backend SHALL NOT authorize corpus reads solely because an account has the service_agent role. A machine account SHALL read only roots with its explicit viewer or editor grant and their descendants; mutations SHALL require an editor grant. Delegated callers SHALL continue to use the human team policy. The evaluation application and its configuration SHALL remain outside this change.

#### Scenario: Same role does not confer another source’s rights
- **GIVEN** two distinct accounts with the service_agent role and only the first has a grant on a root
- **WHEN** they list or directly read that root’s folders
- **THEN** only the first account receives their contents
- **AND** unauthorized roots are excluded before listing pagination

#### Scenario: Read-only machine account cannot mutate
- **GIVEN** a machine account has an explicit viewer grant on a corpus root
- **WHEN** it attempts to ingest or modify content under that root
- **THEN** the operation is refused without an editor grant

### Requirement: Retire unused global corpus surfaces
The knowledge-flow backend SHALL remove the unused /documents/metadata/search route and the /corpus filesystem area, including their unused implementation helpers. Team workspace filesystem paths SHALL remain supported. Corpus navigation and content reads SHALL use the existing dedicated document tools, with no compatibility adapter for retired paths.

#### Scenario: Retired filesystem corpus path is refused
- **WHEN** a client requests a filesystem operation on /corpus/...
- **THEN** the backend rejects the unknown filesystem area
- **AND** does not query corpus metadata or document permissions

#### Scenario: Folder refresh remains scoped
- **WHEN** an existing document UI action refreshes its folder
- **THEN** it reloads that folder through its supplied refresher
- **AND** makes no global metadata search request


### Requirement: Label reads follow current team and conversation selection
The system SHALL scope UI label suggestions to the displayed team. Agent label searches SHALL use the conversation team and the union of selected folders and documents, constrained by current corpus authorization before SQL totals and pagination. With no selections, the authorized team is the scope. Requests without a team SHALL be rejected explicitly.

#### Scenario: Mixed selection cannot widen the team
- **WHEN** a conversation selects folder A and one document in folder B, plus an identifier belonging to another team
- **THEN** label results contain matching documents from A and the selected document from B within the conversation team
- **AND** foreign-team identifiers affect neither results nor totals

#### Scenario: Suggestions do not disclose another team's labels
- **WHEN** the user opens label management in team A
- **THEN** labels used only in team B are absent from suggestions, even if the user can also read team B


### Requirement: Report partial metadata and index mutation failures
After committing document metadata, the system SHALL report a vector-index update failure explicitly. It SHALL retain the committed metadata and SHALL NOT add compensating cleanup or automatic recovery for this case.

#### Scenario: Renaming or retrievability update fails in the index
- **WHEN** PostgreSQL saves the requested document change and the vector-index client raises an error
- **THEN** the API returns an error explaining that metadata was saved but index updating failed and manual verification is required
- **AND** no rollback, cleanup or additional index attempt is performed


### Requirement: Reject ingestion batches atomically on active-document conflict
The system SHALL reject a complete new ingestion batch before shared corpus writes when any requested document already has an active ingestion. Existing ingestion SHALL continue unchanged.

#### Scenario: One busy document in a batch of ten
- **WHEN** a caller submits ten documents and one already has an active ingestion
- **THEN** none of the ten receives a new admission or shared corpus write
- **AND** the existing task continues, with no cancellation or partial admission

#### Scenario: Existing UI selection spans multiple requests
- **WHEN** the existing upload UI splits a selection into several backend requests and one request has an active-document conflict
- **THEN** the backend rejects that whole request and other requests may proceed independently
- **AND** upload-only mode remains available without launching document processing, using the same conflict admission rule before shared writes

### Requirement: Tabular access uses folder authorization and independent attachments
The system SHALL resolve tabular corpus inventories from authorized team folders in SQL, without document permission enumeration or a service-role bypass. Explicit document requests SHALL load only the requested metadata. Owned conversation attachments SHALL remain outside corpus listings and SHALL NOT require corpus team permission when requested alone.

#### Scenario: Large team tabular inventory
- **WHEN** a team reader lists 5,001 tabular documents in that team's folders
- **THEN** all documents are eligible without a document ListObjects call or a document-count-dependent set of permission checks

#### Scenario: Attachment owner lacks corpus permission
- **WHEN** a caller requests only their own valid tabular conversation attachment and lacks access to the selected corpus team
- **THEN** attachment ownership authorizes the request independently of corpus rights
- **AND** this grants no access to corpus documents or another user's attachments

### Requirement: Atomic folder rename

Renaming a corpus folder SHALL use one UI mutation and one backend SQL transaction for the folder name and all descendant paths. Document membership and folder IDs SHALL remain unchanged. A database error SHALL roll back the whole rename.

#### Scenario: Rename a populated subtree
- **WHEN** an editor renames a folder containing nested folders and documents
- **THEN** the backend updates the complete subtree from its stored inventory, independently of the UI snapshot
- **AND** a name conflict leaves the original subtree unchanged


### Requirement: Replacement imports follow corpus admission

A confirmed replacement SHALL retain the existing document UID and its single destination folder. The backend SHALL resolve replacement identities before admitting the complete request and SHALL admit it before shared metadata, content or index mutations. Existing import decision and progress behavior SHALL remain available.

#### Scenario: An existing replacement target is busy
- **WHEN** one selected replacement already has an active ingestion
- **THEN** the backend refuses the new batch before any shared document write or index purge
- **AND** the existing ingestion continues unchanged

#### Scenario: Replacement target disappeared
- **WHEN** a confirmed replacement target no longer exists at planning or preparation time
- **THEN** that file produces an explicit error requiring a new import
- **AND** the backend does not create a new document automatically

#### Scenario: Replacement target changed folders
- **WHEN** the planned replacement now belongs to another folder
- **THEN** replacement fails without modifying that document or its artifacts
