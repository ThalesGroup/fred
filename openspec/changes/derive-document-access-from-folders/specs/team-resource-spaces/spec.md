## ADDED Requirements

### Requirement: Folder candidates retain object authorization

Knowledge Flow SHALL select document and resource candidates from stored membership intersected with authorized folders, then enforce the object READ permission before exposing them. Stored membership SHALL NOT authorize an object on its own. Documents and resources SHALL never be globally enumerated for authorization. When a request carries a team, personal or library scope, the authorized folders SHALL be that scope's folders. Tabular discovery, description, queries and value search, document metadata listing, label lookups and resource listing SHALL follow this rule.

#### Scenario: Workbook beyond the first thousand readable documents

- **GIVEN** a caller can read 3,000 documents and a tabular workbook sits in a library of the agent's team scope
- **WHEN** the agent lists, describes, queries or searches tabular documents in that scope
- **THEN** the workbook is listed, described, queryable and found
- **AND** no document-level authorization enumeration is performed

#### Scenario: Document outside the authorized folders

- **WHEN** a document belongs only to folders the caller cannot read
- **THEN** it is absent from listings, labels and tabular resolution

#### Scenario: Labels over a large corpus

- **GIVEN** a caller can read more documents than a SQL statement can bind as individual parameters
- **WHEN** the caller lists labels or resolves documents by label
- **THEN** the result covers every readable document carrying those labels

#### Scenario: Completed removal followed by a stale metadata or resource save

- **GIVEN** an object belongs to A and B, and a reader can read A but not B
- **WHEN** removal from A completes before an older metadata or resource save resumes and restores A only in SQL
- **THEN** the reader of A cannot see metadata, labels, label totals, resource content or tabular datasets
- **AND** the reader of B keeps access
- **AND** the same denial holds for already-existing SQL drift without a repair

#### Scenario: Label pagination excludes denied candidates

- **GIVEN** denied and allowed documents share a label and SQL folder membership
- **WHEN** the reader pages through that label
- **THEN** sorting, totals and offsets count only allowed documents, with no holes caused by denied candidates

#### Scenario: Authorization failure and bounded concurrency

- **WHEN** candidate authorization fails
- **THEN** the request fails instead of returning partial results or treating the failure as a denial
- **AND** at most ten object permission checks run concurrently per request

#### Scenario: Existing special authorization paths

- **WHEN** a service agent without a delegation caller role reads its authorized team corpus
- **THEN** the existing team-scoped exception remains effective
- **AND** delegated callers remain subject to person-level authorization
- **AND** disabled corpus ReBAC does not expose another uploader's tagless attachment

### Requirement: Possibly truncated authorization enumerations are logged

Every remaining OpenFGA object enumeration SHALL keep failing on authorization errors, and SHALL log a warning when its response reaches the server's default result limit or nears its default deadline.

#### Scenario: Enumeration at the result limit

- **WHEN** an enumeration returns 1,000 objects
- **THEN** a `possibly_truncated` warning names the object type, relation and count, without the subject

#### Scenario: Enumeration below the limits

- **WHEN** an enumeration returns fewer than 1,000 objects quickly
- **THEN** no warning is logged
