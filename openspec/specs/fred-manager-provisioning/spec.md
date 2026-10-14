# Fred Manager Provisioning

## Purpose

Provision Fred identities and organization/team spaces through an authenticated
Rust CLI, with the complete assignable role catalog and enforceable permissions.

## Requirements

### Requirement: Complete scoped role model

The system SHALL support cumulative space roles `member`, `editor`, `admin` and
`analyst` on organizations, teams and projects. Member, editor and analyst SHALL
grant local content read; only editor SHALL grant generic content write; only
admin SHALL grant local governance. Analyst SHALL grant evaluation execution,
evaluation-corpus management and evaluation conversation read. Admin SHALL grant
the first two evaluation permissions but SHALL NOT grant conversation or generic
content read. Editor SHALL NOT grant evaluation authority.

The system SHALL support platform roles `platform_admin`, `platform_observer`,
`team_manager`, `feature_manager` and `prompt_editor`. Admin SHALL provide all
platform permissions; observer SHALL provide platform observation; team manager
SHALL provide team creation and registry listing; feature manager SHALL provide
capability/application management and registry listing; prompt editor SHALL
provide platform prompt editing. No platform role SHALL imply a space role,
space content permission or project access. Authorization decisions SHALL be
queryable for the authenticated caller even for operations implemented separately.

#### Scenario: Every role has distinct positive and negative permissions
- **WHEN** each role is granted alone and in combinations
- **THEN** its effective permissions match the complete role matrix above
- **AND** permissions in other spaces remain denied without explicit local roles

#### Scenario: Analyst obeys parent membership and revocation rules
- **WHEN** an analyst holds a child-space role and analyst is their last content
  role on its parent
- **THEN** revoking the parent role is refused, including under concurrent writes
- **AND** an additional parent member or editor role permits analyst revocation

### Requirement: Protected and observable role administration

Role APIs SHALL expose direct grants separately from effective roles, preserve
cumulative grants, and support independent grant/revoke of all assignable roles.
Space role changes SHALL retain the existing personal-space and parent-membership
constraints and SHALL NOT remove the last admin of a non-personal space, including
under concurrent revocations. Revocation SHALL NOT synthesize a member/content
grant; explicit remaining roles alone determine access. Platform role
administration SHALL require platform admin. Each platform grant target SHALL
exist in Keycloak; missing users or unverifiable directory state SHALL prevent the
write. Revocation SHALL remain possible for a deleted non-root identity. Granting
or revoking platform admin SHALL additionally require the completed bootstrap's
root identity; revoking that root SHALL be forbidden. Import SHALL apply the same
grant protection. An absent direct platform grant SHALL return not-found on
revocation, including when its permission is inherited through platform admin.

#### Scenario: Concurrent revocations preserve an administrator
- **WHEN** two requests attempt to revoke the last two admins of a non-personal
  organization, team or project
- **THEN** at most one succeeds and at least one admin remains
- **AND** neither revocation adds implicit content membership

#### Scenario: Nonexistent identity cannot receive platform authority
- **WHEN** an authorized caller grants a platform role to an unknown subject, or
  Keycloak cannot verify its existence
- **THEN** the operation fails without writing a role tuple
- **AND** removal of stale grants for deleted non-root users remains possible

#### Scenario: Import cannot bypass root protection
- **WHEN** a non-root platform admin imports a bundle declaring a platform admin
- **THEN** import fails before any identity, space or role mutation
- **AND** the same caller can import a bundle containing only other roles

#### Scenario: Direct roles and effective roles remain distinguishable
- **WHEN** the caller holds only a direct platform-admin grant
- **THEN** `/me` reports all five effective platform roles
- **AND** role administration lists only the direct admin grant
- **AND** revoking an absent direct observer grant returns not-found

#### Scenario: Delegated team management does not grant space content
- **WHEN** a team manager creates a team under an existing organization, naming
  an initial admin who holds a parent content role
- **THEN** the team is created with that explicit admin and no role for the caller
- **AND** the caller cannot use this permission to create a project or change an
  existing team's roles
- **AND** registry listing exposes metadata, never content

### Requirement: Compatible and fully validated bundle

The CLI SHALL accept an organization object containing a nonempty `name` and
nonempty `admins` username list, plus `users` using the control-plane entry fields
`username`, `email`, `first_name`, `last_name`, `password`, `teams`, `team_roles`,
and `platform_roles`. Organization admins SHALL refer to entries in `users`.
Team roles SHALL accept `team_member`, `team_editor`, `team_admin`, `team_analyst`.
Platform roles SHALL accept legacy `admin`/`observer`, canonical
`platform_admin`/`platform_observer`, and `team_manager`, `feature_manager`,
`prompt_editor`. Equivalent aliases SHALL be deduplicated.

Within each user entry, a `teams` name SHALL imply member only when that entry
has no explicit role for that team. Explicit roles SHALL accumulate. Organization
admins SHALL receive explicit organization admin and member grants. Every team-role
holder SHALL receive an explicit organization member grant. Platform-only users
SHALL receive no space grant. Duplicate usernames, unknown fields or roles, empty
names, malformed declarations, and missing declared admins for new teams SHALL
fail preflight before writes. Lifecycle states such as `pending_team_admin` SHALL
NOT be accepted as assignable roles or promoted silently to admin.

#### Scenario: All established roles can be provisioned
- **WHEN** a valid bundle declares every assignable role, including analyst and
  the three delegated platform roles
- **THEN** every requested direct grant is applied with its defined permissions
- **AND** none is ignored, downgraded or treated as a placeholder

#### Scenario: Admin-only team membership grants no team content
- **WHEN** an entry names a team in `teams` and explicitly requests only
  `team_admin` for that team
- **THEN** it receives team admin and organization member, but no team member

#### Scenario: Invalid tail does not partially provision a valid prefix
- **WHEN** the last entry has an unknown role, duplicate username, unresolved
  passwordless identity or an uncreatable team
- **THEN** the entire preflight fails without creating the earlier identities

### Requirement: Verified operator and separate service identity

Import SHALL require a valid caller bearer and a current OpenFGA platform-admin
grant. Disabled authentication and non-Keycloak identity mapping SHALL be refused.
The CLI SHALL authenticate and authorize before mutating database schema, FGA
store/model, identities, spaces or grants. Keycloak credentials and client roles
SHALL NOT substitute for the operator's Fred permission. The CLI SHALL use its
own configured service account to resolve/create identities, and SHALL NOT depend
on the HTTP server or Temporal being available.

#### Scenario: Unauthorized commands have no side effects
- **WHEN** a caller is unauthenticated, has an invalid/expired token, holds only
  observer/delegated roles, or supplies only service credentials
- **THEN** import exits nonzero and no provisioning or initialization write occurs

### Requirement: Identity preservation and service account provisioning

Existing users SHALL be resolved by exact username without changing their profile
or password. Missing users SHALL require a nonempty password and be created
enabled with a non-temporary password; absent email SHALL use the control-plane
`<username>@example.com` fallback. Username lookup SHALL handle pagination and
ambiguity explicitly. A concurrent create conflict SHALL be re-resolved and
validated rather than accepted blindly. fred-manager SHALL declare its own factory
service client and the query-users, view-users and manage-users realm grants.
Secrets SHALL be referenced through configured environment variable names.

#### Scenario: Existing identity is preserved on replay
- **WHEN** a bundle supplies new profile/password values for an existing username
- **THEN** the original subject is reused without any profile/password update

#### Scenario: Concurrent identity creation is recoverable
- **WHEN** another import creates the username after lookup
- **THEN** the importer resolves exactly that username and uses its subject
- **AND** an unresolved or ambiguous conflict fails explicitly

### Requirement: Additive replay under concurrent authorization changes

Import SHALL identify an organization by root name and a team by organization
and name, rejecting incompatible or personal-space collisions. Replay SHALL
reuse committed identities/spaces, repair missing requested grants and preserve
undeclared existing grants. A changed name SHALL identify a different space.
Every mutation SHALL check the caller's current authority while serialized with
relevant revocations. Parent content grants SHALL precede child roles and preserve
the parent/child invariant even across errors and retries. Partial dependency
failure SHALL report failure without claiming distributed rollback or deleting
created users. Success SHALL mean all declared state was reconciled.

#### Scenario: Resume after dependency failure
- **WHEN** an import fails after identity or space creation and is retried
- **THEN** committed IDs are reused, missing grants are repaired, and no duplicate
  spaces or destructive role replacements occur

#### Scenario: Revocation precedes a waiting import
- **WHEN** the caller's platform authority or a required parent role is revoked
  while import waits for the corresponding mutation lock
- **THEN** the waiting mutation rechecks the new state and cannot violate it

### Requirement: Safe operational feedback

The command SHALL return a nonzero exit code on failure and report the failing
phase and safe reconciliation counts. Output, logs and errors SHALL NOT expose
passwords, bearer tokens, client secrets or raw upstream response bodies. A
partial failure SHALL identify replay as the recovery action. Role mutations
SHALL record actor, target subject, role, scope and outcome using Fred's structured
logging conventions.

#### Scenario: Dependency echoes a credential
- **WHEN** Keycloak or another dependency returns an error containing a submitted
  secret, or parsing fails near a password field
- **THEN** neither normal nor error output contains the secret or raw payload
