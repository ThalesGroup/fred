## ADDED Requirements

### Requirement: No implicit version is assigned on import

The system SHALL NOT assign a document an implicit version relative to another
document of the same name, and SHALL NOT refuse an import on the grounds that an
alternate version already exists. Same-name handling is the user's explicit
decision.

#### Scenario: A same-named file is imported

- **WHEN** a user imports a file whose name already exists in the destination folder
- **THEN** the outcome is the overwrite or skip they chose
- **AND** no third state such as an alternate version is created

#### Scenario: A third same-named file is imported

- **WHEN** a name has already been imported twice before
- **THEN** the import is not refused on version grounds

### Requirement: No alternate version is promoted on deletion

When a document is deleted, the system SHALL NOT search for another document to
promote in its place. Deleting a document SHALL NOT change any other document.

#### Scenario: A document is deleted from a large corpus

- **WHEN** a document is deleted
- **THEN** no other document is renamed or modified
- **AND** the deletion cost does not grow with the total number of documents on the platform

### Requirement: Existing alternate versions become ordinary documents

Documents that carry an alternate version at migration time SHALL become
ordinary documents with a name distinct from their base document. No document
SHALL be deleted by the migration, and none SHALL remain hidden.

A document whose name no other document in any of its folders holds SHALL keep
that name: there is nothing for it to be confused with.

#### Scenario: A folder holds a base document and its alternate version

- **WHEN** the migration runs on a folder holding "report.pdf" and its alternate version
- **THEN** both documents are listed in that folder afterwards
- **AND** their names differ from each other
- **AND** their content and identifiers are unchanged

#### Scenario: An alternate version outlived the document it was an alternate of

- **WHEN** the migration runs on an alternate version whose name no other document in its folders holds
- **THEN** it keeps the name it has
- **AND** it is an ordinary document afterwards

### Requirement: The versioning fields leave the document contract

The document identity SHALL NOT declare `canonical_name` or `version`, and the
system SHALL ignore both keys wherever a stored document still carries them.

The migration SHALL NOT rewrite a document it does not rename. Nearly every
stored document carries `version: 0` — the retired model defaulted it — so
clearing the key everywhere would rewrite the whole table for data nothing reads,
inside the single transaction Alembic wraps a migration in.

#### Scenario: An ordinary document is migrated

- **WHEN** the migration runs on a document that carried `version = 0`
- **THEN** its name is unchanged
- **AND** its stored JSON is not rewritten

#### Scenario: A document still carrying the retired keys is read

- **WHEN** a document whose stored JSON carries `canonical_name` or `version` is read
- **THEN** neither key appears in its identity
- **AND** the read succeeds
