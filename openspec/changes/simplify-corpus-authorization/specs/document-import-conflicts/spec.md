## MODIFIED Requirements

### Requirement: Overwrite preserves the document identity

When the user chooses to overwrite, the system SHALL replace the content of the
existing document and SHALL preserve its `document_uid`, single folder and owning space.
It SHALL NOT create a second document, retain the previous content indexed, or
adopt a document from another folder or space.

#### Scenario: A cited document is overwritten

- **WHEN** a document referenced by an existing agent answer is overwritten
- **THEN** that reference still resolves
- **AND** it resolves to the new content

#### Scenario: Re-indexing follows an overwrite

- **WHEN** a document is overwritten
- **THEN** its previous extracted content and vectors are replaced by the new ones
- **AND** a search no longer returns the previous content

#### Scenario: Quota reflects the difference only

- **WHEN** a 2 MB document is overwritten by a 3 MB file
- **THEN** the team's storage usage increases by 1 MB, not by 3 MB

#### Scenario: The same name exists in another folder

- **WHEN** a file is imported into a folder with no same-name document but that
  name exists elsewhere
- **THEN** it creates an independent document in the destination folder
- **AND** the other document's identity, content and folder remain unchanged
