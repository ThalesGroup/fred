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


### Requirement: Canonical provisioning identities
Provisioning SHALL reject usernames that differ from their lowercase form, contain
control characters or have surrounding whitespace before any writes. It SHALL NOT
normalize declared usernames silently. Before creating any identity it SHALL reject
conflicting effective emails among missing identities and with existing directory
accounts. Existing identities SHALL retain their profiles. The supported Keycloak
realm SHALL disallow duplicate emails. External concurrent directory changes MAY
still fail after preflight and SHALL retain the additive replay contract.

#### Scenario: A noncanonical username cannot create a partial identity
- **WHEN** a bundle declares `Alice` or a username with surrounding whitespace
- **THEN** the whole bundle is refused before identity or authorization writes

#### Scenario: Email conflict cannot create a prefix
- **WHEN** missing identities have conflicting explicit or generated emails, or an email is already in use
- **THEN** the whole bundle is refused before any identity creation

### Requirement: Known organization owner identities
New organization owner grants, including operator creation and import, SHALL
verify that the target subject exists in the configured Keycloak directory before
publishing ownership. Unavailable verification SHALL fail closed. Revocation
SHALL NOT require the identity to still exist. Bootstrap SHALL continue to act
only on its own verified human OIDC identity, never an asserted subject.

#### Scenario: A fictitious owner cannot protect removal of the real owner
- **WHEN** a platform owner attempts to name an unknown organization owner
- **THEN** no owner tuple is written and the existing last-owner protection remains effective

### Requirement: Content existence at mutation dispatch
Document and folder mutations SHALL recheck existence under the organization lock
before SQL changes or external dispatch. An object deleted while the caller waits
SHALL return not-found without dispatch or a fabricated mutation success.

#### Scenario: Deletion wins over a waiting ingestion or rename
- **WHEN** deletion commits while an ingestion or rename waits for the organization lock
- **THEN** the waiter returns not-found and submits no workflow

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

### Requirement: Compatible and fully validated bundle

The CLI and HTTP import SHALL accept only the current version-2 ZIP containing
exactly `manifest.json`, `users.json`, `organizations.json`, `teams.json` and
`projects.json`. The manifest SHALL declare `format_version: 2`,
`users_schema_version: 2`, `source_platform: "swift"`; the four data files SHALL
be arrays. Old JSON inputs and version-1 ZIPs SHALL fail with `not_yet_supported`
before provisioning writes; no conversion or compatibility adapter SHALL run.
Unsupported versions or sections SHALL likewise be rejected, never ignored.

Users SHALL declare unique nonempty usernames, optional identity fields `email`,
`first_name`, `last_name`, `password`, and optional `platform_roles`. Platform
roles SHALL use the current owner model; only `owner` and `observer` SHALL alias
`platform_owner` and `platform_observer`. Removed role names SHALL be rejected. Every space SHALL
contain unique nonempty `ref`, nonempty `name` and a `roles` map from declared
usernames to arrays of `member`, `editor`, `admin`, `analyst`, plus `owner` on organizations. Teams SHALL reference
an organization through `organization`; projects SHALL reference a team through
`team`. All parents SHALL be declared in the bundle. At least one organization
SHALL exist; an empty projects array SHALL be accepted.

All declared roles SHALL be cumulative; repeated equivalent grants SHALL be
deduplicated. Import SHALL NOT synthesize undeclared content roles. A new space
SHALL require a declared admin; a new organization SHALL also require a declared
owner. Child grants SHALL require declared or existing direct parent content roles, checked before writes and under mutation locks. Duplicate
usernames/references/sibling names/JSON keys, unknown fields/roles, undeclared
parents/subjects, malformed archives and predictable identity/state conflicts
SHALL fail whole-bundle preflight without provisioning a valid prefix.

#### Scenario: All established roles can be provisioned
- **WHEN** a valid ZIP declares every assignable role, including analyst and the
  three delegated platform roles
- **THEN** every requested direct grant is applied with its defined permissions
- **AND** none is ignored, downgraded or treated as a placeholder

#### Scenario: Admin-only team membership grants no team content
- **WHEN** the ZIP declares organization member and only team admin for a person
- **THEN** that person receives exactly those roles and no team content role

#### Scenario: Invalid tail does not partially provision a valid prefix
- **WHEN** the last entry has an unknown role, duplicate username, unresolved
  passwordless identity or an uncreatable team or project
- **THEN** the entire preflight fails without creating earlier identities

#### Scenario: Complete project provisioning
- **WHEN** a valid ZIP declares organization and team content membership plus
  project admin for Alice
- **THEN** Alice can administer that project without project content access
- **AND** all other declared roles retain their distinct permissions

#### Scenario: Invalid parent membership rejects the whole bundle
- **WHEN** a project-role holder has only admin on its parent team and no declared
  or existing parent content role
- **THEN** no identity, space or role is provisioned from the bundle

#### Scenario: Old input is explicitly unsupported
- **WHEN** the caller submits the old JSON or Python version-1 ZIP
- **THEN** import reports `not_yet_supported` without provisioning writes

### Requirement: Verified operator and separate service identity

Import SHALL require a valid caller bearer and a current OpenFGA platform-owner
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

## REMOVED Requirements

### Requirement: Protected and observable role administration
**Reason**: Root-only platform-admin administration and delegated team management are replaced by platform and organization owners.
**Migration**: Replaced by "Owner-protected role administration" and "Platform and organization owners".
