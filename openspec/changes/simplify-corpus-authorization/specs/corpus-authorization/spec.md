## Purpose

Authorize corpus access consistently through the containing folder while keeping
authorization work bounded independently of the number of documents it holds.

## ADDED Requirements

### Requirement: A corpus document has one immutable folder

Every corpus document SHALL belong to exactly one existing folder. Creation,
overwrite, synchronization and import SHALL enforce this invariant; document
links and moves SHALL NOT be supported. Session attachments SHALL retain their
separate owner/session isolation and SHALL NOT become unfiled corpus documents.

#### Scenario: A producer attempts to change membership
- **WHEN** an API, source sync or archive supplies zero/multiple folders or tries
  to attach an existing document to another folder
- **THEN** the operation is explicitly rejected before document content or
  membership changes, and the original document remains intact

#### Scenario: An attachment is accessed outside its session authority
- **WHEN** a caller has corpus-folder access but lacks the attachment's existing
  owner/session authorization
- **THEN** that folder access does not grant access to the attachment

### Requirement: Folder permissions govern every corpus access path

The system SHALL authenticate callers through the existing identity boundary and
use ReBAC folder permissions for corpus operations. It SHALL resolve membership
from canonical metadata, not a caller-supplied folder or search index. Read SHALL
require folder READ; document update, deletion and processing SHALL require folder
UPDATE. No metadata, content, counts, citations or tool results SHALL bypass this
rule, including service-principal and agent calls.

#### Scenario: A caller supplies an authorized folder for another document
- **WHEN** a requested document belongs to an unauthorized folder, despite the
  supplied scope or stale index claiming an authorized folder
- **THEN** no document information or content is returned

#### Scenario: A reader attempts a mutation
- **WHEN** a caller can read the folder but cannot update it
- **THEN** reading is allowed and document update, deletion and processing are denied

### Requirement: Authorization work has a finite request bound

The system SHALL enforce finite scope, page, candidate and retry limits.
Authorization checks for a fixed folder-scoped operation SHALL NOT grow with its
document count. Folder discovery and unscoped retrieval SHALL inspect bounded
candidate pages and expose continuation/incompleteness, never silently present a
truncated authorization set as complete. Over-limit inputs SHALL be rejected.

#### Scenario: The same folder grows from hundreds to many thousands of documents
- **WHEN** the same content-page, count or scoped-search request is repeated
- **THEN** its number of authorization checks and maximum transport calls remain
  within the same bound, without enumerating readable documents

#### Scenario: A candidate page contains only denied folders
- **WHEN** more candidates remain beyond that page
- **THEN** the response discloses no denied data and provides continuation rather
  than incorrectly declaring the authorized result set exhausted

### Requirement: Requested scopes and revocations fail closed

An explicitly requested scope SHALL NOT be broadened. Any unauthorized requested
folder SHALL cause rejection. Authorization-service failure SHALL NOT yield corpus
data. A completed permission revocation SHALL be respected by subsequent requests;
already authorized in-flight operations need not be cancelled.

#### Scenario: A mixed scope includes a denied folder
- **WHEN** a user or agent requests both readable and unreadable folders
- **THEN** the request is rejected, without falling back to global search

#### Scenario: Permission is revoked between requests
- **WHEN** a grant is revoked successfully before the next content or agent request
- **THEN** that request cannot use an earlier positive authorization result

### Requirement: Folder browsing separates summaries from contents

Folder summaries SHALL NOT enumerate contained document identifiers or metadata.
Contents SHALL be paginated separately; counts and sizes SHALL cover only the
authorized scope. Result-label enrichment SHALL NOT fetch folder contents.

#### Scenario: Many search hits belong to one large folder
- **WHEN** folder labels are added to the returned hits
- **THEN** no scan of that folder's documents is performed

### Requirement: Lifecycle operations preserve the authorization boundary

Concurrent creation/deletion and retried ingestion SHALL NOT produce accessible
orphan documents. Removed canonical documents SHALL NOT remain accessible through
stale indexes. Target-format exports/imports SHALL preserve single membership and
folder grants; incompatible legacy input SHALL be explicitly rejected.

#### Scenario: Deletion leaves stale search data
- **WHEN** search returns a candidate whose canonical document or folder is gone
- **THEN** the candidate's content and metadata are withheld

#### Scenario: Ingestion races with folder deletion
- **WHEN** a worker attempts to commit a document after its folder is deleted
- **THEN** no orphan corpus document becomes accessible and cleanup remains retryable
