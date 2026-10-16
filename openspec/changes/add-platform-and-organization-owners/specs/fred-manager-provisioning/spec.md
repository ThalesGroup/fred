## ADDED Requirements

### Requirement: Platform and organization owners
The platform SHALL have one technical role, `platform_owner`, and each organization
a technical `owner` role. An owner SHALL hold no content permission, and an
organization owner's role SHALL NOT descend to teams or projects. Platform owners
SHALL grant and revoke platform owners, the other platform roles and organization
owners. Organization owners SHALL grant and revoke the organization's admins.
Revoking the last platform owner, or the last owner of an organization, SHALL be
refused, including under concurrent revocations. `owner` SHALL only be granted on
organizations.

#### Scenario: Root names another platform owner
- **WHEN** root grants `platform_owner` to Paula and Paula revokes root's grant
- **THEN** both operations succeed and Paula is the only platform owner
- **AND** Paula's own revocation is refused as the last platform owner

#### Scenario: An organization owner names admins without content
- **WHEN** the platform owner makes Olga owner of TSN and Olga names Bob admin of TSN
- **THEN** Bob manages TSN and its descendants
- **AND** Olga reads no content of TSN and cannot create a team in it

#### Scenario: Owner on a team is refused
- **WHEN** a caller grants `owner` on a team or project
- **THEN** the request is refused without a role write

### Requirement: Owner-protected role administration
Role APIs SHALL expose direct grants separately from effective roles, preserve
cumulative grants, and support independent grant/revoke of all assignable roles.
Space role changes SHALL retain the existing personal-space and parent-membership
constraints and SHALL NOT remove the last admin of a non-personal space or the last
owner of an organization, including under concurrent revocations. Revocation SHALL
NOT synthesize a member/content grant; explicit remaining roles alone determine
access. Platform role administration SHALL require platform owner. Each platform
grant target SHALL exist in Keycloak; missing users or unverifiable directory state
SHALL prevent the write. Revocation SHALL remain possible for a deleted identity.
Import SHALL apply the same grant protection. An absent direct platform grant SHALL
return not-found on revocation, including when its permission is inherited through
platform owner.

#### Scenario: Concurrent revocations preserve an administrator
- **WHEN** two requests attempt to revoke the last two admins of a non-personal
  organization, team or project
- **THEN** at most one succeeds and at least one admin remains
- **AND** neither revocation adds implicit content membership

#### Scenario: Nonexistent identity cannot receive platform authority
- **WHEN** an authorized caller grants a platform role to an unknown subject, or
  Keycloak cannot verify its existence
- **THEN** the operation fails without writing a role tuple
- **AND** removal of stale grants for deleted users remains possible

#### Scenario: Import requires a platform owner
- **WHEN** a caller without `platform_owner` imports a bundle
- **THEN** import fails before any identity, space or role mutation

#### Scenario: Direct roles and effective roles remain distinguishable
- **WHEN** the caller holds only a direct platform-owner grant
- **THEN** `/me` reports all four effective platform roles
- **AND** role administration lists only the direct owner grant
- **AND** revoking an absent direct observer grant returns not-found

#### Scenario: Teams are created by organization admins only
- **WHEN** a platform owner without a role in TSN creates a team in TSN
- **THEN** the request is refused
- **AND** an admin of TSN creates it, naming an initial admin who holds a direct
  TSN content role

## MODIFIED Requirements

### Requirement: Complete scoped role model

The system SHALL support cumulative space roles `member`, `editor`, `admin` and
`analyst` on organizations, teams and projects, and `owner` on organizations.
Member, editor and analyst SHALL grant content read; only editor SHALL grant generic
content write; only admin SHALL grant governance of spaces and their roles. Editor,
admin and analyst SHALL also apply to every descendant space; member and owner SHALL
NOT. Analyst SHALL grant evaluation execution, evaluation-corpus management and
evaluation conversation read. Admin SHALL grant the first two evaluation permissions
but SHALL NOT grant conversation or generic content read. Editor SHALL NOT grant
evaluation authority. Owner SHALL grant only the administration of the
organization's admins.

The system SHALL support platform roles `platform_owner`, `platform_observer`,
`feature_manager` and `prompt_editor`. Owner SHALL provide all platform permissions;
observer SHALL provide platform observation; feature manager SHALL provide
capability/application management and registry listing; prompt editor SHALL
provide platform prompt editing. No platform role SHALL imply a space role,
space content permission or project access. Authorization decisions SHALL be
queryable for the authenticated caller even for operations implemented separately.

A role on a child space SHALL require the target's direct member, editor or analyst
role on its parent. Access inherited from an ancestor SHALL NOT satisfy it.

#### Scenario: Every role has distinct positive and negative permissions
- **WHEN** each role is granted alone and in combinations
- **THEN** its effective permissions match the complete role matrix above, in its
  space and, for descending roles, in each descendant
- **AND** permissions in unrelated spaces remain denied

#### Scenario: Analyst obeys parent membership and revocation rules
- **WHEN** an analyst holds a child-space role and analyst is their last content
  role on its parent
- **THEN** revoking the parent role is refused, including under concurrent writes
- **AND** an additional parent member or editor role permits analyst revocation

#### Scenario: Inherited access does not replace parent membership
- **WHEN** Bob is editor of TSN without a direct role on team A
- **THEN** granting Bob a role on project P under A is refused
- **AND** revoking Bob's editor role on TSN never leaves a project role without a
  direct content role on its parent

### Requirement: Authenticated HTTP ZIP import

`POST /fred-manager/v1/import-export/import` SHALL accept one multipart `file`,
requiring verified platform-owner authority before upload reading. It SHALL use the
same identity and reconciliation behavior as the CLI. A new organization SHALL
declare at least one owner and one admin, possibly the same person; `owner` SHALL be
refused on teams and projects. It SHALL return HTTP 200 with reconciliation counts
only after successful completion, never a fabricated task ID or early success.
Importer failures SHALL retain safe phase/count information. Early upload, parsing
and authorization failures SHALL use `detail` without reconciliation counts. All
errors SHALL use Fred's `detail` envelope and never expose credentials, input bodies
or upstream bodies.
Old/unsupported input SHALL return HTTP 422 with `not_yet_supported`.

ZIP data SHALL be read without extraction and bounded to 50 MiB compressed and
100 MiB expanded actual bytes. Duplicate entries, non-root paths, symlinks,
encryption and corrupt data SHALL be rejected before provisioning. HTTP failures
or disconnects SHALL NOT be described as proof of rollback or absence of effects.

#### Scenario: Authorization cannot be bypassed through HTTP
- **WHEN** a caller without `platform_owner` imports the ZIP
- **THEN** the request fails before provisioning effects

#### Scenario: Archive failure cannot provision a prefix
- **WHEN** the last file is malformed, corrupt, duplicated or expands past the limit
- **THEN** import fails without creating any identity, space or grant

### Requirement: Manager-authorized provisioning page

The UI SHALL offer provisioning to manager platform owners using manager authority, independently of control-plane administrative roles. Fred's existing administration navigation SHALL expose the page after personal terms acceptance and manager bootstrap completion. The page SHALL accept a ZIP, prevent duplicate submissions while pending, display completion counts only after success, and present failures with additive-replay guidance without claiming rollback.

#### Scenario: Complete and replay an import
- **GIVEN** an admitted manager platform owner
- **WHEN** the operator opens Provisioning through Fred's administration navigation and imports the Make-generated demo ZIP
- **THEN** the page shows the completed identity, space and grant counts from the service
- **AND** replay preserves committed identities and space IDs

#### Scenario: Authority unavailable or denied
- **WHEN** manager authority is loading, unavailable or excludes platform owner
- **THEN** the page does not enable provisioning, including on a direct URL visit
- **AND** it distinguishes an unavailable authority service from a confirmed access refusal

#### Scenario: Rejected or interrupted import
- **WHEN** the service rejects a legacy ZIP, returns an import failure, or the connection is lost
- **THEN** the page shows an error and no success report for that attempt
- **AND** it explains that effects can remain and replay requires correcting the cause

### Requirement: Platform-only root onboarding
The first-person UI SHALL present terms before the existing secret-gated root bootstrap. It SHALL use manager state and generated manager calls only. Bootstrap SHALL grant only platform ownership, preserving exclusive claimant recovery and permanent completion. It SHALL NOT create an organization or enroll the root in one. Errors and retries SHALL remain explicit, and an unavailable status service SHALL NOT admit the UI.

#### Scenario: Fresh platform root
- **WHEN** a person accepts terms and supplies the valid deployment secret on a fresh platform
- **THEN** they become platform owner and can open provisioning
- **AND** the platform contains no spaces and that person has no implicit organization membership
- **AND** reloading does not reopen bootstrap

#### Scenario: Wrong secret or completed bootstrap
- **WHEN** the secret is invalid or bootstrap has already completed
- **THEN** the existing 403 or 409 feedback is shown without granting a new root

## REMOVED Requirements

### Requirement: Protected and observable role administration
**Reason**: Root-only platform-admin administration and delegated team management are replaced by platform and organization owners.
**Migration**: Replaced by "Owner-protected role administration" and "Platform and organization owners".
