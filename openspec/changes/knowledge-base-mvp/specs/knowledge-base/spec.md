## Purpose

Defines the observable contract for pulling external data into FRED as an indexed knowledge base: which knowledge base types a team may use, what a created knowledge base instance guarantees about its own scope and content identity, and how a source connector's discovered changes must behave so synchronization never duplicates, loses, or silently corrupts work.

## ADDED Requirements

### Requirement: A knowledge base type is registered platform-wide, not created per team
A knowledge base type (its pipeline kind, push/pull mode, and — for pull — its connector kind) SHALL be defined once for the whole deployment, never authored or duplicated by an individual team.

#### Scenario: Two teams see the same knowledge base type definition
- **WHEN** two different teams are each authorized to use the same registered knowledge base type
- **THEN** both observe identical `kind`/`mode`/`connector_kind` values for that type — neither team can define its own variant

### Requirement: A team may create a knowledge base instance only of a knowledge base type it is authorized to use
Creating a knowledge base instance SHALL fail closed unless the knowledge base type is registered and enabled in the deployment, and the requesting team is explicitly authorized to use that knowledge base type.

#### Scenario: Creation succeeds for an enabled, authorized type
- **GIVEN** a knowledge base type is registered and enabled in the deployment
- **AND** the requesting team is authorized to use that knowledge base type
- **WHEN** the team creates a knowledge base instance of that type
- **THEN** the knowledge base instance is created and scoped to that team

#### Scenario: Creation is refused for an unregistered or disabled type
- **GIVEN** a knowledge base type id that the deployment does not register, or has disabled
- **WHEN** any team attempts to create a knowledge base instance of that type
- **THEN** creation fails and no knowledge base instance is created

#### Scenario: Creation is refused for a team without authorization
- **GIVEN** a knowledge base type that is registered and enabled in the deployment
- **AND** the requesting team is not authorized to use that knowledge base type
- **WHEN** the team attempts to create a knowledge base instance of that type
- **THEN** creation fails and no knowledge base instance is created

### Requirement: Authorization to use a knowledge base type governs creation only, never content access
Authorization to use a knowledge base type SHALL determine only whether a team may create or operate an instance of that type. It SHALL NOT determine, expand, or restrict which documents any knowledge base instance's content is scoped to.

#### Scenario: Content scope is unaffected by type authorization
- **GIVEN** a team authorized to use a knowledge base type creates an instance scoped to its own team and tags
- **WHEN** that instance is queried for its content
- **THEN** the content returned reflects only the instance's own team/tag scope, unaffected by which teams are authorized to use the knowledge base type

### Requirement: A source connector reports a stable identity independent of its display path
Each item a source connector discovers SHALL carry an identity and a revision that are stable across repeated discovery calls, independent of the item's display path, so that a rename is representable without being treated as a deletion plus a new item.

#### Scenario: An unchanged item produces no reported change
- **WHEN** a source connector discovers changes twice in a row with nothing modified at the source in between
- **THEN** the second discovery reports no changes for that item

#### Scenario: A changed item is reported with its stable identity intact
- **WHEN** an item's content changes at the source between two discovery calls
- **THEN** the discovery reports a change for that item's same stable identity, with an updated revision

### Requirement: Deletion at the source is reported as a distinct, first-class change
A source connector SHALL report that an item was removed from the source as its own explicit kind of change, not left for the caller to infer by comparing listings.

#### Scenario: A removed item is reported as a deletion
- **WHEN** an item present in a prior discovery call is no longer present at the source
- **THEN** the next discovery call reports that item's removal explicitly

### Requirement: Pull-sourced documents are indistinguishable from pushed documents downstream
A document ingested through a pull-mode knowledge base instance SHALL be represented in FRED's document store the same way as a manually uploaded document, so that downstream systems (search, metadata, deletion) need no separate code path for its origin.

#### Scenario: A pulled document is retrievable like any other document
- **WHEN** a source connector's discovered change is ingested into a knowledge base instance
- **THEN** the resulting document is retrievable through the same document metadata access used for manually uploaded documents

### Requirement: A knowledge base instance never runs two overlapping synchronizations against its own state
For any single knowledge base instance, at most one synchronization SHALL be actively updating that instance's state at a time.

#### Scenario: A second synchronization does not start while one is in progress
- **GIVEN** a knowledge base instance's synchronization is currently in progress
- **WHEN** another synchronization for that same knowledge base instance is requested
- **THEN** the second synchronization does not run concurrently against the same instance state

### Requirement: A knowledge base synchronization is accepted, then completed, independently of when its documents become queryable
Acceptance, completion, and per-document queryability SHALL be three distinct, separately observable states of a synchronization.

#### Scenario: Acceptance is durable before any document is processed
- **WHEN** a synchronization for a knowledge base instance is accepted
- **THEN** a durable record of that synchronization exists before any document has been processed, independent of whether the requesting caller is still connected

#### Scenario: A knowledge base is queryable incrementally, not only once its synchronization completes
- **GIVEN** a synchronization for a knowledge base instance is in progress
- **WHEN** one of its discovered changes has been durably ingested
- **THEN** that document is queryable immediately, without waiting for the synchronization to reach a terminal state

### Requirement: A replayed synchronization submission never creates a duplicate run
Requesting a synchronization for a knowledge base instance that already has one accepted and not yet terminal SHALL NOT start a second one.

#### Scenario: Resubmitting after a lost response does not start a second synchronization
- **GIVEN** a synchronization for a knowledge base instance has already been accepted and is not yet in a terminal state
- **WHEN** the same knowledge base instance's synchronization is requested again (for example, a client retry after a lost response)
- **THEN** no second synchronization is accepted for that instance, and the caller observes that one is already in progress

#### Scenario: A synchronization requested after the previous one finished is a new, independent run
- **GIVEN** a knowledge base instance's most recent synchronization has reached a terminal state
- **WHEN** its synchronization is requested again
- **THEN** a new synchronization is accepted, and it reports no changes for anything already durably captured

### Requirement: A crash between ingesting a change and recording it neither loses nor duplicates that change
Resubmitting an item already durably ingested under its current source revision SHALL NOT create a second document for it.

#### Scenario: Resubmitting an already-ingested item is a no-op, not a duplicate
- **GIVEN** an item was already durably ingested into a knowledge base instance under its current source revision
- **WHEN** that same item, at the same revision, is submitted again (for example, after a crash before its cursor advance was durably recorded)
- **THEN** no second document is created for that item, and the instance's document count for that item is unchanged

### Requirement: An update that fails leaves the previously ingested version of the affected document in place
A source item's content change SHALL NOT remove the item's previously ingested document until its replacement has durably landed.

#### Scenario: A failed update does not remove the previously ingested version
- **GIVEN** a source item that was previously ingested successfully
- **AND** that item's content has since changed at the source
- **WHEN** ingesting the new revision fails partway through
- **THEN** the previously ingested version remains queryable, and the item is retried whole on the next synchronization

### Requirement: A knowledge base instance's synchronization never writes to its remote source
Discovering and fetching changes from a source SHALL be read-only with respect to that source, both in what the connector's contract exposes and in the credential it is provisioned with.

#### Scenario: Discovering and fetching changes never mutates the source
- **WHEN** a synchronization discovers and fetches changes from a knowledge base instance's remote source
- **THEN** the remote source's own content is unaffected by that discovery or fetch

#### Scenario: A connector's source credential carries no write permission
- **GIVEN** a knowledge base type's connector is provisioned with a credential or mount to reach its remote source
- **WHEN** that credential or mount is inspected
- **THEN** it grants read access only — no write, update, or delete permission on the source is present

### Requirement: An internal mutation is authorized by the execution's own bound scope, never by a caller-supplied identifier alone
A request to create, delete, or otherwise mutate a document on a knowledge base instance's behalf SHALL be checked against three things together — the caller's authorized identity, the knowledge base bound to the executing synchronization, and the target document's own recorded ownership — and refused if any one of them disagrees. A knowledge base identifier supplied by the caller SHALL NOT, by itself, establish authorization to mutate that knowledge base.

#### Scenario: Deleting a document requires its knowledge base to match both the request and the executing synchronization's own bound scope
- **GIVEN** a document that belongs to one knowledge base instance
- **AND** a synchronization is executing on behalf of a different knowledge base instance
- **WHEN** that synchronization issues a delete request naming the first document
- **THEN** the deletion is refused and the document is not removed, regardless of what knowledge base identifier the request itself carries

#### Scenario: An unauthenticated or unauthorized caller cannot mutate any knowledge base's documents
- **GIVEN** a request to submit or delete a document, carrying a knowledge base identifier that does match a real knowledge base instance
- **WHEN** the caller is not the authorized execution identity for that knowledge base's current synchronization
- **THEN** the mutation is refused

### Requirement: A worker no longer recognized as the active executor of a synchronization cannot complete further mutations under it
Once a synchronization has been reconciled to a terminal state by anything other than the worker that was executing it, that worker SHALL NOT be able to complete any further document mutation attributed to that synchronization.

#### Scenario: A superseded worker's mutation is rejected after its synchronization is reconciled terminal
- **GIVEN** a synchronization was reconciled to a terminal state while its original worker was still attempting to process an item
- **WHEN** that original worker attempts a further document mutation under that synchronization's identity
- **THEN** the mutation is refused

### Requirement: A knowledge base type's usage authorization is re-verified on every synchronization, not only at creation
Revoking a team's authorization to use a knowledge base type SHALL stop future synchronizations of that team's instances without deleting the instances or their content.

#### Scenario: A synchronization does not run once its team's authorization is revoked
- **GIVEN** a knowledge base instance was created while its team was authorized to use its knowledge base type
- **AND** that authorization has since been revoked
- **WHEN** a synchronization for that instance is requested
- **THEN** the synchronization does not run

#### Scenario: Revocation does not remove already-ingested content
- **GIVEN** a knowledge base instance whose team's authorization to use its knowledge base type has been revoked
- **WHEN** that instance's previously ingested documents are queried
- **THEN** they remain queryable, subject only to the existing document-level access rules

### Requirement: A pulled document is queryable through both semantic search and tabular query, like any other document
A knowledge base instance's kind SHALL NOT determine which retrieval paths its content can appear in; a document's tag scope alone determines that, identically to a manually uploaded document.

#### Scenario: A knowledge base instance's documents are retrievable by semantic search
- **GIVEN** a knowledge base instance whose documents carry its own scope tag
- **WHEN** an agent capability configured for that tag performs a semantic search
- **THEN** the knowledge base instance's ingested documents are included in the results, through the same retrieval path as a manually uploaded document carrying that tag

#### Scenario: A knowledge base instance's tabular documents are queryable by SQL
- **GIVEN** a knowledge base instance whose documents carry its own scope tag and include tabular content
- **WHEN** an agent capability scoped to that tag runs a query over that tabular content
- **THEN** the knowledge base instance's ingested tabular documents are queried through the same path as a manually uploaded tabular document carrying that tag

#### Scenario: A chat user retrieves an authorized knowledge base's content without configuring any synchronization detail themselves
- **GIVEN** a team's admin has already authorized the team's knowledge base type and an agent has already been configured with capability access scoped to that knowledge base's tag
- **WHEN** a user of that team asks the agent a question answerable from that knowledge base's content
- **THEN** the user receives an answer drawn from that content, without the user having supplied, seen, or needed to know about any connector cursor, synchronization task, or MCP server configuration

### Requirement: Creating or operating a knowledge base instance never configures an agent capability
A knowledge base type or instance SHALL NOT create, modify, or imply any agent capability or tool configuration.

#### Scenario: Creating a knowledge base instance does not configure any agent
- **WHEN** a team creates a knowledge base instance
- **THEN** no agent capability or MCP server configuration is created, modified, or implied as a result

### Requirement: A synchronization's progress record never carries a resolved credential or secret
Every event a synchronization emits SHALL be safe to display without redaction.

#### Scenario: A connector's credential reference never appears in an emitted event
- **WHEN** a synchronization emits a progress or terminal event for a knowledge base instance
- **THEN** that event's content contains no resolved credential and no secret value — only whatever identifies the knowledge base instance and the item being processed
