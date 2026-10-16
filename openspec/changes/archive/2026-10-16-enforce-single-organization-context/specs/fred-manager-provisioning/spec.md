## ADDED Requirements

### Requirement: A person has one organization context

A person SHALL hold roles in at most one organization per Fred instance, including
governance-only roles and personal-space grants. All supported assignment paths
SHALL reject a second attachment, including concurrent imports and direct grants.
Business context SHALL be resolved on the server from canonical OpenFGA roles and
placement of committed spaces. Missing context grants no business access; ambiguous
context SHALL fail closed. Platform roles SHALL NOT imply organization membership.

#### Scenario: Bob enters TSN
- **WHEN** Bob is attached to TSN and signs in after satisfying personal admission
- **THEN** Fred enters TSN on `/home` without an organization parameter or selector
- **AND** foreign space/document identifiers grant no business access

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
- **THEN** business context is refused, including direct API access
- **AND** an authorized administrator can revoke that person's roles using the
  existing dependency and last-owner/admin rules without automatic deletion

#### Scenario: Platform-only account
- **WHEN** a platform account has no organization roles
- **THEN** personal consent and authorized platform administration remain available
- **AND** no organization or content authority is implicitly granted

## MODIFIED Requirements

### Requirement: Imported person enters declared organization

After ZIP import Fred's existing home and space navigation SHALL display the caller's
unique declared organization and authorized space memberships and roles from manager
authority. Home SHALL default to that organization without a URL organization
identifier or selector. Explicit team/project selection SHALL remain within that
context. Changing accounts SHALL clear the prior person's session data. An imported
person SHALL accept terms personally before accessing this view. Platform administration
alone SHALL NOT expose organization content or create membership. The journey SHALL
make no control-plane, knowledge-flow or agent-runtime calls and SHALL expose only
its implemented destinations.

#### Scenario: Root imports and switches to a member
- **WHEN** root imports the Make-generated ZIP, signs out through Fred's account
  menu, and a declared member signs in
- **THEN** root sees the real import report and no automatic organization membership
- **AND** the member accepts terms and enters their organization with navigation
  to their declared teams/projects and roles
- **AND** the member cannot open provisioning without the required platform role

#### Scenario: Select a declared space
- **WHEN** an admitted person selects a declared team or project in home navigation
- **THEN** Home shows that membership's name, hierarchy and roles
- **AND** no agent or document page is opened and no membership is created
