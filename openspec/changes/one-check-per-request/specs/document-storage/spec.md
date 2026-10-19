## MODIFIED Requirements

### Requirement: Storage is authorized by the owning space

Manager SHALL require current admission and the owning space's effective Write
permission for upload, and Read permission for listing, receipts and original
download. Publication SHALL revalidate the writer after transfer. OpenFGA SHALL
remain canonical for roles and hierarchy; folders and documents SHALL NOT acquire
independent grants. A target in another organization SHALL return 403; an
authorization dependency failure SHALL return 503.

#### Scenario: Effective content roles and administrative roles differ
- **WHEN** users with direct/inherited editor, analyst, member, admin, organization owner and platform roles exercise the document routes
- **THEN** the implemented space permission model determines each result
- **AND** administration alone does not grant content access and personal ownership does not widen another space's access

#### Scenario: Access changes during upload
- **WHEN** access or admission is revoked before the publication transaction is authorized
- **THEN** no document is published and the pending bytes become eligible for cleanup

#### Scenario: A caller supplies a foreign identifier
- **WHEN** a caller targets another organization's folder, document or receipt
- **THEN** the request returns 403 and reveals neither metadata nor content and performs no mutation
