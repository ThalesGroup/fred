## ADDED Requirements

### Requirement: Folder membership changes reach the search index

When a vectorized document is linked to, unlinked from, or refiled between
folders, Knowledge Flow SHALL update the folder ids carried by every indexed
chunk of that document before reporting the change as successful, on every
supported vector store. A failure to update the index SHALL fail the request.
Search SHALL NOT add a per-query membership lookup to achieve this.

#### Scenario: Link an indexed document to a second folder

- **GIVEN** a vectorized document belongs to folder A
- **WHEN** an authorized user links it to folder B
- **THEN** a corpus search restricted to B can return the document
- **AND** a corpus search restricted to A still can

#### Scenario: Unlink an indexed document from one of its folders

- **GIVEN** a vectorized document belongs to folders A and B
- **WHEN** an authorized user removes it from A
- **THEN** a corpus search restricted to A no longer pre-selects it
- **AND** a corpus search restricted to B still returns it

#### Scenario: Refile a synchronized document

- **WHEN** library sync moves a vectorized document from folder A to folder B
- **THEN** its chunks carry only B

#### Scenario: The index update fails

- **WHEN** the vector store rejects the folder update during a link or unlink
- **THEN** the request fails
- **AND** the document's stored membership, storage charge and folder relation are unchanged

#### Scenario: Document without vectors

- **WHEN** a document that was never vectorized is linked or unlinked
- **THEN** the membership change succeeds without touching the vector store
