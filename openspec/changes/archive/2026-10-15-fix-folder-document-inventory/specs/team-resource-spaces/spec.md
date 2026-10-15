## ADDED Requirements

### Requirement: Known folder documents are authorized independently of global inventory size

Explicit document reads and single/multiple-folder document inventories SHALL evaluate the existing document permissions for their stored candidates without relying on a complete global list of readable documents. Paginated browsing SHALL retain its current ordering, offsets, limits and stored-total semantics. Authorization work SHALL depend on the selected candidates and use bounded concurrency.

#### Scenario: Small folder within a large readable corpus

- **GIVEN** a user can read more than 1,000 documents and a selected folder contains 20 readable documents
- **WHEN** the user lists that folder or requests a page covering its 20 documents
- **THEN** all 20 documents are returned regardless of which objects a global authorization inventory would include
- **AND** documents elsewhere do not add document checks to that request

#### Scenario: Shared document in several selected folders

- **GIVEN** one document belongs to two selected folders
- **WHEN** their document inventories are resolved together
- **THEN** its READ decision is evaluated once within that candidate batch
- **AND** its membership in both folders is preserved

#### Scenario: A stored candidate is unreadable

- **WHEN** the user's document READ permission is denied for a stored listing candidate
- **THEN** that document is excluded without widening the user's access

#### Scenario: Authorization cannot be evaluated

- **WHEN** authorization of a known candidate fails because the authority is unavailable
- **THEN** the request fails explicitly instead of interpreting the failure as an empty readable inventory

### Requirement: Folder deletion does not treat unreadable or unresolved contents as absent

Document-folder deletion SHALL use canonical stored subtree and document membership. It SHALL retain existing folder and document permission checks, refuse denied or unresolved contents before mutation, and refuse final folder removal while known document links remain. Subtrees SHALL remain bounded by owner, type and path boundaries. This requirement does not guarantee atomicity with concurrent ingestion or repair partial external-store cleanup failures.

#### Scenario: Delete a populated folder above the authorization inventory cap

- **GIVEN** a readable corpus larger than 1,000 documents, an authorized folder containing 20 documents, no concurrent writers and healthy stores
- **WHEN** the user deletes that folder
- **THEN** every stored document membership is processed before the folder is removed
- **AND** last-membership documents, their vectors and content are removed through the existing deletion path and quota is released once

#### Scenario: One candidate cannot be processed

- **GIVEN** the canonical folder inventory contains a document whose READ authorization is denied or fails
- **WHEN** the user requests folder deletion
- **THEN** the request fails before mutating the subtree rather than omitting that document

#### Scenario: Membership remains after removal attempts

- **WHEN** processing returns but a canonical document link to the folder still exists
- **THEN** the folder is retained and the operation reports failure

#### Scenario: Document also belongs outside the deleted subtree

- **GIVEN** a document belongs to the deleted subtree and another surviving folder
- **WHEN** the subtree is deleted
- **THEN** only its subtree memberships are removed
- **AND** the document, content, vectors and surviving access remain available

#### Scenario: Same folder path under another owner

- **GIVEN** two owners have folders with the same path
- **WHEN** one owner's subtree is deleted
- **THEN** the other owner's folders and documents are unchanged
