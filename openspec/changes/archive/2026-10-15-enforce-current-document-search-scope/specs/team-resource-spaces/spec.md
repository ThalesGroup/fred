## ADDED Requirements

### Requirement: Corpus search respects current contextual membership

Corpus search SHALL return only documents authorized for the caller and currently belonging to the requested ownership context. Explicit document selection SHALL NOT bypass that context. Library and document selections SHALL form a union within that context; a document-only selection SHALL NOT enable a whole-library search. These guarantees SHALL hold for semantic, strict and hybrid search.

#### Scenario: Multi-team user names a document from another team

- **GIVEN** a user belongs to teams A and B and a document belongs only to B
- **WHEN** the user searches in team A with that document ID, alone or alongside an A library
- **THEN** no content or source metadata from the B document is returned
- **AND** an authorized selected A document remains searchable

#### Scenario: Mixed and document-only selections retain their meaning

- **GIVEN** two authorized libraries and several documents inside the same team
- **WHEN** a user selects one library and a document in the other
- **THEN** eligible results can come from either selected source
- **WHEN** the user selects only that document
- **THEN** other corpus documents are excluded

### Requirement: Stale index membership cannot authorize corpus search hits

Corpus search SHALL validate candidate documents against current canonical membership and the caller's applicable read authorization before exposing their content or source metadata. Missing canonical metadata SHALL exclude the candidate. An unavailable authorization authority SHALL fail the search rather than permit unchecked results.

#### Scenario: Shared document is removed from the selected library

- **GIVEN** a document belonged to libraries A and B and now belongs only to B
- **AND** the search index still records both libraries
- **WHEN** a user searches only library A
- **THEN** no content or source metadata from that document is returned
- **AND** this remains true even if an obsolete read grant survives
- **WHEN** an authorized B reader searches B
- **THEN** the document remains searchable

#### Scenario: Candidate metadata is absent or permission is denied

- **WHEN** the index returns a corpus candidate whose canonical metadata is absent or whose read permission is denied
- **THEN** the candidate is excluded while other eligible candidates remain available

#### Scenario: Authorization cannot be established

- **WHEN** authorization fails because the authority is unavailable
- **THEN** the request fails without returning unchecked corpus hits

### Requirement: Corpus selection preserves enabled conversation attachments

Enabled attachment search SHALL remain scoped to the authenticated user and current session independently of corpus library or document selection. Search SHALL use the current indexed sources on each turn and preserve configured source ceilings.

#### Scenario: Late attachment with a selected corpus document

- **GIVEN** a conversation has already completed a turn
- **AND** a new attachment has completed ingestion and indexing for that user and session
- **WHEN** another turn searches with an authorized corpus document selected and attachments enabled
- **THEN** the attachment remains eligible alongside that corpus document
- **AND** another user or session cannot retrieve the attachment

#### Scenario: Late library document in the same conversation

- **GIVEN** a conversation has already completed a turn using a selected library
- **WHEN** another document finishes indexing in that library and the conversation searches again
- **THEN** that document is eligible without recreating the conversation

#### Scenario: Attachments are disabled

- **WHEN** attachment search is disabled for the request
- **THEN** selecting corpus documents does not enable attachment retrieval
