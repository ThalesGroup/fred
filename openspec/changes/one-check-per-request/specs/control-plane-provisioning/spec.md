## MODIFIED Requirements

### Requirement: A person has one organization context

A person SHALL hold roles in at most one organization per Fred instance, including
governance-only roles and personal-space grants. All supported assignment paths
SHALL reject a second attachment, including concurrent imports and direct grants.
Business access SHALL be decided by the OpenFGA Check on the target space alone; a
target in another organization SHALL return 403. `/me/spaces` SHALL report committed
roles resolving to more than one organization as a conflict. Platform roles SHALL NOT
imply organization membership.

#### Scenario: Bob enters TSN
- **WHEN** Bob is attached to TSN and signs in after satisfying personal admission
- **THEN** Fred enters TSN on `/home` without an organization parameter or selector
- **AND** a space, folder or document of another organization returns 403 and no content

#### Scenario: Concurrent conflicting assignments
- **WHEN** two writers attach the same person to distinct organizations concurrently
- **THEN** at most one attachment succeeds and the other reports a conflict
- **AND** an abandoned stale write cannot publish after a newer guarded assignment

#### Scenario: Import declares conflicting attachments
- **WHEN** an import declares a person in two organizations or adds a second known attachment
- **THEN** preflight refuses before creating identities, spaces or role grants
- **AND** a conflict introduced after preflight is rechecked before publication

#### Scenario: Existing ambiguous data and recovery
- **WHEN** a person's committed roles resolve to more than one organization
- **THEN** `/me/spaces` returns 409 and each business request is decided by its own Check
- **AND** an authorized administrator can revoke that person's roles using the
  existing dependency and last-owner/admin rules without automatic deletion

#### Scenario: Platform-only account
- **WHEN** a platform account has no organization roles
- **THEN** personal consent and authorized platform administration remain available
- **AND** no organization or content authority is implicitly granted

#### Scenario: One Check per business request
- **WHEN** a member reads a directory, whatever the number of roles they hold
- **THEN** authorization uses the target's placement Reads and one read Check, with no Read of the caller's roles

### Requirement: Folder filters belong to the authorized space

Manager directory listing SHALL enforce current personal admission and space read permission. A supplied parent/folder identifier SHALL belong to the requested space; a missing or foreign folder SHALL return 404 rather than a successful empty list. Admin and organization owner roles alone SHALL NOT grant content access; local members and effective editors/analysts SHALL retain their existing read semantics.

#### Scenario: Filter outside the requested space
- **WHEN** a reader supplies a nonexistent folder or a folder belonging to another space to either list endpoint
- **THEN** the endpoint returns 404 without exposing folder contents

#### Scenario: Direct API refusal and current grants
- **WHEN** a person without content read authority requests a list, including an organization's administrator or a reader whose grant has been revoked
- **THEN** the endpoint refuses the request and returns no rows
- **AND** an authorized content reader or editor still obtains only the requested space and folder's metadata
