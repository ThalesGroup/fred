## MODIFIED Requirements

### Requirement: Authorized resource browsing in the provisioned space journey

Fred SHALL retain its existing Resources route, full document workspace, navigation, controls and styles. Resources SHALL use manager for folders and current space authority, without requiring knowledge-flow availability or treating manager folder IDs as knowledge-flow tags. The separate knowledge-base consumer SHALL retain its existing contract. Failures SHALL retain ordinary UI feedback without a reduced replacement page or fabricated success. Existing document controls SHALL remain present, with sending explicitly unavailable from upload, drop, import retry/resume and selected-folder actions.

#### Scenario: Priya browses personal and collective resources
- **WHEN** admitted Priya opens her personal space or fredlab and then Resources
- **THEN** Fred mounts the original resource workspace for the selected identifier with manager folder data and current space write decisions
- **AND** an unavailable non-migrated dependency retains its original error/loading behavior rather than a fabricated empty success

#### Scenario: Document pagination
- **WHEN** a caller pages through manager document metadata for an authorized folder
- **THEN** the manager cursor traverses name/id pages without duplicates or omissions for unchanged data
- **AND** an eventual UI binding SHALL preserve the existing pagination presentation without inventing totals or conflating folder identifiers with another service's identifiers

#### Scenario: Refusal, failure and revalidation
- **WHEN** a caller without current read authority requests a manager folder or document list
- **THEN** manager refuses without returning content
- **AND** a failed service request SHALL NOT become a fabricated successful UI response or grant

### Requirement: Authorized folder creation in Resources

Manager SHALL support folder creation at the root or inside a folder of a personal, team or project space for an admitted caller with current effective write permission. Creation SHALL make no Temporal call; its governance router SHALL require no ingestion client. The server MUST enforce the person's unique organization and current write authority; administration, membership or analyst rights alone SHALL NOT grant content writes. Fred SHALL use its original folder dialog with the manager operation and current space/parent identifiers.

#### Scenario: Create and browse
- **WHEN** an authorized editor creates a folder through manager in an authorized location
- **THEN** the folder is persisted there and appears in the corresponding manager folder listing
- **AND** the original Resources dialog creates through this operation and refreshes the current directory

#### Scenario: Revocation and isolation
- **WHEN** a caller lacks write permission, loses it before a waiting write is admitted, or targets another person's private space or another organization
- **THEN** manager refuses creation without inserting a folder

#### Scenario: Repeated submission and navigation
- **WHEN** the user submits the original folder dialog or changes resource location
- **THEN** the original dialog remains recognizable and preserves entered values on failure
- **AND** the manager binding SHALL prevent concurrent duplicate submissions and prevent a late response from changing a different location

## ADDED Requirements

### Requirement: Folder lifecycle preserves containment without document effects

Every folder SHALL have one immutable owning space and at most one parent in that space. Sibling names SHALL be unique, roots included. Names SHALL retain current normalization/validation and the explicit depth bound of 15. Rename SHALL preserve descendants and their identifiers. Recursive deletion SHALL be atomic for each requested document-free subtree and SHALL refuse that entire subtree operation if a document is present. Multiple selected roots MAY succeed independently, with truthful reporting and refresh; confirmation wording SHALL describe that folder-only contract. No folder operation SHALL add a canonical folder grant.

#### Scenario: Conflict, concurrent change or document-bearing subtree
- **WHEN** a name conflicts, authority is revoked while a mutation waits, or any descendant contains a document
- **THEN** the invalid mutation is refused with no partial subtree deletion or document effect
- **AND** two concurrent creations of the same sibling name produce at most one folder

### Requirement: Folder navigation has measured bounded costs

Navigation SHALL return bounded directory pages with deterministic ordering, truthful totals of matching immediate folders and directory-scoped search/sort. Creation dates SHALL be real; document-derived size SHALL remain unknown, with the existing folder size-sort fallback to name. No synthetic document page SHALL be mixed into the folder result. Unrelated folder trees SHALL NOT be downloaded or enumerated to show a directory. Folder count and nesting depth SHALL add zero OpenFGA tuples and no per-folder authorization calls. Membership-dependent authorization and concurrent-write costs SHALL be measured and documented separately from folder-volume costs.

#### Scenario: Large directory and unrelated tree
- **WHEN** a space contains 10,000 folders, including a wide directory and a deep branch
- **THEN** navigation returns only a bounded requested page and uses parent-selective SQL access for an unfiltered directory
- **AND** increasing folders alone leaves authorization request and stored tuple counts unchanged
- **AND** focused concurrent measurements report fixture size, memberships, latency, query plans and lock behavior without claiming universal performance
