## ADDED Requirements

### Requirement: Document visibility derives from authorized folders

Knowledge Flow SHALL determine readable documents and resources from their stored folder membership intersected with the caller's authorized folders, never from an enumeration of readable documents or resources. When a request carries a team, personal or library scope, the authorized folders SHALL be that scope's folders. Tabular discovery, description, queries and value search, document metadata listing, label lookups and resource listing SHALL follow this rule.

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

### Requirement: Possibly truncated authorization enumerations are logged

Every remaining OpenFGA object enumeration SHALL keep failing on authorization errors, and SHALL log a warning when its response reaches the server's default result limit or nears its default deadline.

#### Scenario: Enumeration at the result limit

- **WHEN** an enumeration returns 1,000 objects
- **THEN** a `possibly_truncated` warning names the object type, relation and count, without the subject

#### Scenario: Enumeration below the limits

- **WHEN** an enumeration returns fewer than 1,000 objects quickly
- **THEN** no warning is logged
