## ADDED Requirements

### Requirement: Document surface is read-only
Manager SHALL expose document metadata reads and authorization probes, but SHALL NOT register document creation, rename, deletion or ingestion operations. OpenAPI and the generated frontend client SHALL expose the same surface. Existing metadata SHALL remain intact and subject to current organization, retirement and content authorization checks.

#### Scenario: Provisional mutations are unavailable
- **WHEN** a caller requests POST `/documents`, PATCH or DELETE `/documents/{id}`, or POST `/documents/{id}/ingest`
- **THEN** the API returns 404 for absent paths or 405 for unsupported methods on the retained GET path
- **AND** no document mutation or workflow submission occurs

#### Scenario: Resources remains usable without Temporal
- **WHEN** PostgreSQL, OpenFGA and configured identity dependencies are available but Temporal is unreachable
- **THEN** the API starts and serves authorized folder/document reads and folder operations
- **AND** the separate space-deletion worker retains its Temporal dependency and configured cleanup behavior

### Requirement: Folder existence at mutation dispatch
Folder mutations SHALL recheck existence under the organization lock before SQL changes.
A folder deleted while the caller waits SHALL return not-found without a fabricated mutation success.

#### Scenario: Deletion wins over a waiting rename
- **WHEN** deletion commits while a folder rename waits for the organization lock
- **THEN** the waiter returns not-found and does not mutate a replacement or fabricate success

## MODIFIED Requirements

### Requirement: Retirement closes all manager business entry points
After acceptance, manager SHALL omit the retired scope from business lists and
refuse direct reads, writes, permission/scope probes, role changes, new descendants,
provisioning reuse and personal-space reuse in that scope.
Mutation waiters SHALL recheck retirement after locking. Requests authorized before
retirement can finish; retirement SHALL NOT authorize new content access.
Names and personal-space slots SHALL remain reserved until physical cleanup.
Remaining direct roles on retired rows SHALL continue to count for the unique
organization attachment, even after partial hierarchy cleanup. No membership
copy or automatic role repair SHALL be introduced.

#### Scenario: Folder creation or provisioning waits behind deletion
- **WHEN** deletion commits while creation or import is waiting for its mutation lock
- **THEN** the waiter refuses the retired destination without creating folders, spaces, grants or dispatching work

#### Scenario: Organization deletion cannot bypass account isolation
- **WHEN** a person's old organization is pending cleanup and they still hold its direct roles
- **THEN** assigning them roles in another organization remains refused
- **AND** their UI has no active workspace in the retired organization

#### Scenario: Old activity follows recreation
- **WHEN** a deleted name is recreated with a new UUID and an old cleanup activity is retried
- **THEN** the new space and its roles remain untouched


## REMOVED Requirements

### Requirement: Content existence at mutation dispatch
**Reason**: Document mutations are retired; the retained folder guarantee is specified separately.
**Migration**: Folder callers retain existence rechecks; document mutation callers receive 404/405.
