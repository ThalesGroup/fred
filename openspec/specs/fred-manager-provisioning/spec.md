# Fred Manager Provisioning

## Purpose

Provision Fred identities and organization/team/project spaces through authenticated
Rust CLI and HTTP ZIP import, with the complete assignable role catalog and enforceable permissions.

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

The CLI and HTTP import SHALL accept only the current version-2 ZIP containing
exactly `manifest.json`, `users.json`, `organizations.json`, `teams.json` and
`projects.json`. The manifest SHALL declare `format_version: 2`,
`users_schema_version: 2`, `source_platform: "swift"`; the four data files SHALL
be arrays. Old JSON inputs and version-1 ZIPs SHALL fail with `not_yet_supported`
before provisioning writes; no conversion or compatibility adapter SHALL run.
Unsupported versions or sections SHALL likewise be rejected, never ignored.

Users SHALL declare unique nonempty usernames, optional identity fields `email`,
`first_name`, `last_name`, `password`, and optional `platform_roles`. Existing
platform role names and aliases SHALL retain their meaning. Every space SHALL
contain unique nonempty `ref`, nonempty `name` and a `roles` map from declared
usernames to arrays of `member`, `editor`, `admin`, `analyst`. Teams SHALL reference
an organization through `organization`; projects SHALL reference a team through
`team`. All parents SHALL be declared in the bundle. At least one organization
SHALL exist; an empty projects array SHALL be accepted.

All declared roles SHALL be cumulative; repeated equivalent grants SHALL be
deduplicated. Import SHALL NOT synthesize undeclared content roles. A new space
SHALL require a declared admin. Child grants SHALL require declared or existing
parent content access, checked before writes and under mutation locks. Duplicate
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

### Requirement: Role publication survives unknown remote outcomes

Direct role grants SHALL remain stored in OpenFGA and permission evaluation SHALL
use its authorization model. The correction SHALL NOT replace that role source
with SQL or duplicate the permission matrix in Rust.

Shared role mutation services, including bootstrap and import, SHALL publish
effective grants in an order serialized with relevant parent and actor revocations.
A delayed mutation whose captured revision has been consumed SHALL fail without
role effects. If an uncertain mutation commits first, subsequent mutations SHALL
observe its effects and revalidate their constraints. Timeout, cancellation or
restart SHALL NOT be reported as proof of rollback. A retry SHALL capture current
revisions and reauthorize rather than reuse previous authorization decisions.

Offline cutover SHALL preserve all supported direct grants in the captured source, their permission meanings,
space identities and bootstrap state. Invalid existing state SHALL cause explicit
failure rather than silent grant loss. Failed cutover SHALL NOT expose partial
migration. The new service SHALL NOT fall back to mutable legacy authorization
objects after cutover. Normal CLI import SHALL only verify this initialization.

#### Scenario: Child grant arrives after parent revocation
- **WHEN** a child grant times out before remote completion, parent revocation
  succeeds, and the delayed remote request subsequently completes
- **THEN** the delayed request cannot give effective child access without parent
  content membership

#### Scenario: Platform grant arrives after actor revocation
- **WHEN** a platform grant times out, the root revokes its actor's authority,
  and the original remote write subsequently completes
- **THEN** the delayed write does not make that grant effective
- **AND** a retry by the revoked actor is refused

#### Scenario: Restart does not bypass an intervening revocation
- **WHEN** a process stops with a role write in flight, a conflicting revocation
  succeeds after restart, and the old remote request arrives afterwards
- **THEN** the old request fails without role effects
- **AND** a retry uses fresh authorization and state checks

#### Scenario: An uncertain grant commits before a conflicting mutation
- **WHEN** the original request commits after timeout but before a conflicting
  mutation consumes its captured revision
- **THEN** its role effects are visible to subsequent mutations
- **AND** a mutation with an older revision cannot commit its stale decision
- **AND** the timeout is not described as a rollback

Cutover of existing state SHALL require the explicit local operator command and
operator-established source quiescence. Normal startup SHALL initialize only empty
state. Legacy model semantics, tuple shapes and SQL hierarchy/path consistency
SHALL be validated; parent access SHALL be evaluated by OpenFGA. Published routing
metadata SHALL pin the active store and model IDs, without moving roles into SQL.
Local SQL mutations SHALL hold their organization lock through guarded authorization
and commit. External Keycloak/Temporal operations SHALL be authorized at dispatch;
timeout or revocation SHALL NOT be described as cancellation of remote effects.

#### Scenario: Existing roles survive cutover
- **WHEN** initialized state with all supported roles and completed bootstrap is
  migrated, including a replay after interrupted migration
- **THEN** the direct grants, effective permission matrix and space IDs are preserved
- **AND** bootstrap does not reopen and late legacy writes cannot change effective roles

### Requirement: Explicit OpenFGA query costs

Each changed authorization/import flow SHALL document OpenFGA operation types,
filters, request counts, pagination, tuple volume and sequential/concurrent ordering,
including its SQL lock scope. Cost descriptions SHALL identify their cardinalities
and distinguish client requests from internal OpenFGA evaluation work. Changed
request budgets SHALL have focused verification, including relevant page/batch
boundaries. Scalability claims SHALL identify measured dataset sizes, concurrency,
backend configuration and environment rather than infer capacity from a small demo.

#### Scenario: Import crosses a batch boundary
- **WHEN** an import requires multiple guarded tuple batches
- **THEN** request counts and tuple volumes include the protocol's guard operations
- **AND** no batch exceeds the server's total write-and-delete limit

### Requirement: Demo ZIP built by the established Make command

`make build-demo-bundle` in fred-manager SHALL package the checked-in
`tests/fixtures/import_export/demo_provisioning/` files into
`target/demo-provisioning-bundle.zip`, using the control-plane variable names
`DEMO_PROVISIONING_FIXTURE_DIR` and `DEMO_BUNDLE_FILE`. It SHALL require no running
services. The generated archive SHALL contain the supported five root files and
SHALL be the input of the automated HTTP integration acceptance test.

#### Scenario: Build and import the actual demo artifact
- **WHEN** the Make target runs and its output is imported by an authorized caller
- **THEN** the declared identities, spaces and roles are reconciled
- **AND** importing that output again reuses committed identities and spaces

### Requirement: Authenticated HTTP ZIP import

`POST /fred-manager/v1/import-export/import` SHALL accept one multipart `file`,
requiring verified platform-admin authority before upload reading and root
for any platform-admin grant before provisioning writes. It SHALL use the same
identity and reconciliation behavior as the CLI. It SHALL return HTTP 200 with
reconciliation counts only after successful completion, never a fabricated task
ID or early success. Importer failures SHALL retain safe phase/count information. Early upload, parsing
and authorization failures SHALL use `detail` without reconciliation counts. All
errors SHALL use Fred's `detail` envelope and never expose credentials, input bodies
or upstream bodies.
Old/unsupported input SHALL return HTTP 422 with `not_yet_supported`.

ZIP data SHALL be read without extraction and bounded to 50 MiB compressed and
100 MiB expanded actual bytes. Duplicate entries, non-root paths, symlinks,
encryption and corrupt data SHALL be rejected before provisioning. HTTP failures
or disconnects SHALL NOT be described as proof of rollback or absence of effects.

#### Scenario: Authorization cannot be bypassed through HTTP
- **WHEN** an ordinary user imports the ZIP or a non-root admin requests a
  platform-admin grant
- **THEN** the request fails before provisioning effects

#### Scenario: Archive failure cannot provision a prefix
- **WHEN** the last file is malformed, corrupt, duplicated or expands past the limit
- **THEN** import fails without creating any identity, space or grant

### Requirement: Explicit hierarchy during ZIP reconciliation

Import SHALL resolve organizations by root name, teams by organization/name and
projects by team/name. Bundle references SHALL only resolve declarations within
that bundle. Existing committed target IDs and undeclared grants SHALL be
preserved on replay. Names shared across different parents SHALL remain distinct;
personal-space or incompatible-kind collisions SHALL be refused. Current root,
parent-membership and authority-recheck protections SHALL apply at every level.

#### Scenario: Homonymous spaces remain isolated
- **WHEN** two organizations contain teams and projects with matching names
- **THEN** grants apply only to their explicitly referenced spaces
- **AND** replay creates no duplicate spaces and grants no cross-organization access

### Requirement: Reproducible manager HTTP client

The service SHALL publish a machine-generated OpenAPI contract for its implemented HTTP routes and the frontend SHALL generate its client and types from that contract through Make targets equivalent to the other components. Generation SHALL require neither running services nor runtime secrets. The contract SHALL preserve authentication, request formats, response status/body shapes, enumerated roles, nullability and flattened response fields.

#### Scenario: Deterministic generation
- **WHEN** a developer runs manager `make generate-openapi` and frontend `make update-fred-manager-api` twice
- **THEN** the resulting schema and client are identical and the frontend typechecks
- **AND** `make update-all-apis` includes manager generation

#### Scenario: Binary ZIP transport
- **WHEN** the frontend sends an import through the manager client integration
- **THEN** it sends one multipart `file` with the operator bearer to `/fred-manager/v1/import-export/import`
- **AND** it consumes the generated completed-report type without expecting a task ID

### Requirement: Manager-authorized provisioning page

The UI SHALL offer provisioning to manager platform administrators using manager authority, independently of control-plane administrative roles. Fred's existing administration navigation SHALL expose the page after personal terms acceptance and manager bootstrap completion. The page SHALL accept a ZIP, prevent duplicate submissions while pending, display completion counts only after success, and present failures with additive-replay guidance without claiming rollback.

#### Scenario: Complete and replay an import
- **GIVEN** an admitted manager platform administrator with sufficient authority for the bundle
- **WHEN** the operator opens Provisioning through Fred's administration navigation and imports the Make-generated demo ZIP
- **THEN** the page shows the completed identity, space and grant counts from the service
- **AND** replay preserves committed identities and space IDs

#### Scenario: Authority unavailable or denied
- **WHEN** manager authority is loading, unavailable or excludes platform admin
- **THEN** the page does not enable provisioning, including on a direct URL visit
- **AND** it distinguishes an unavailable authority service from a confirmed access refusal

#### Scenario: Rejected or interrupted import
- **WHEN** the service rejects a legacy ZIP, returns an import failure, or the connection is lost
- **THEN** the page shows an error and no success report for that attempt
- **AND** it explains that effects can remain and replay requires correcting the cause

### Requirement: Repeatable browser acceptance

An automated browser journey SHALL exercise Fred's existing application layout, navigation, OIDC login, manager HTTP API, PostgreSQL and OpenFGA starting without root grants or consent. It SHALL accept terms, bootstrap root through the screen, import the Make-generated ZIP, verify persisted hierarchy and roles, replay without duplicates, sign out and sign in as an imported person, and exercise access refusal and unsupported bundle feedback. No manager or Python shell response SHALL be mocked. Test setup SHALL leave unrelated development data untouched.

#### Scenario: Run browser acceptance repeatedly
- **WHEN** the developer runs the documented browser test command on a machine with its prerequisites
- **THEN** it creates isolated test state, exercises onboarding and import without manual curl or UI actions, and cleans up its services
- **AND** its assertions fail if consent, bootstrap, import, replay, account isolation or authorization behavior regresses
- **AND** it verifies Fred's sidebar, home, administration and logout navigation and fails on calls to services outside this journey

### Requirement: Explicit personal terms acceptance
The manager SHALL expose the active terms version and the caller's persisted acceptance. When enabled, business operations SHALL require acceptance of that version on the server, including bootstrap and import. Acceptance SHALL bind the authenticated person's own subject, submitted active version and server timestamp. It SHALL create no role, organization, team or personal space. Import SHALL NOT accept terms for another person. Repeated acceptance of the same version SHALL preserve the recorded timestamp. Service credentials and delegated assertions SHALL NOT accept terms or bootstrap a root.

#### Scenario: First acceptance and a later version
- **WHEN** a signed-in person has never accepted terms or accepted an older version
- **THEN** the UI requires explicit acceptance and protected API operations fail before side effects
- **AND** accepting the displayed active version survives reload and login
- **AND** a stale submitted version returns 409 without changing acceptance

#### Scenario: Consent has no membership side effects
- **WHEN** a person accepts the active terms
- **THEN** only their acceptance is recorded, without any role or space creation
- **AND** another person's acceptance remains unchanged

### Requirement: Platform-only root onboarding
The first-person UI SHALL present terms before the existing secret-gated root bootstrap. It SHALL use manager state and generated manager calls only. Bootstrap SHALL grant only platform administration, preserving exclusive claimant recovery and permanent completion. It SHALL NOT create an organization or enroll the root in one. Errors and retries SHALL remain explicit, and an unavailable status service SHALL NOT admit the UI.

#### Scenario: Fresh platform root
- **WHEN** a person accepts terms and supplies the valid deployment secret on a fresh platform
- **THEN** they become platform root and can open provisioning
- **AND** the platform contains no spaces and that person has no implicit organization membership
- **AND** reloading does not reopen bootstrap

#### Scenario: Wrong secret or completed bootstrap
- **WHEN** the secret is invalid or bootstrap has already completed
- **THEN** the existing 403 or 409 feedback is shown without granting a new root

### Requirement: Imported person enters declared organization

After ZIP import Fred's existing home and space navigation SHALL display the caller's own declared organization and space memberships and roles from manager authority. Changing accounts SHALL clear the prior person's session data. An imported person SHALL accept terms personally before accessing this view. Platform administration alone SHALL NOT expose organization content or create membership. The journey SHALL make no control-plane, knowledge-flow or agent-runtime calls and SHALL expose only its implemented destinations.

#### Scenario: Root imports and switches to a member
- **WHEN** root imports the Make-generated ZIP, signs out through Fred's account menu, and a declared member signs in
- **THEN** root sees the real import report and no automatic organization membership
- **AND** the member accepts terms and sees their declared organization, teams, projects and roles in Fred's existing home and navigation
- **AND** the member cannot open provisioning without the required platform role

#### Scenario: Select a declared space
- **WHEN** an admitted person selects a declared organization, team or project in the home navigation
- **THEN** the home view shows that membership's name, hierarchy and roles
- **AND** no agent or document page is opened and no membership is created

### Requirement: One Fred UI for the bounded first-user journey

This branch SHALL provide its first-user journey through Fred's existing application, layout, navigation, theme and shared screen components. It SHALL NOT expose a separate manager application or substitute a parallel navigation. CGU SHALL precede bootstrap, and admitted routes SHALL remain unavailable while admission state is loading or cannot be verified. Manager roles SHALL NOT be converted into control-plane permissions to enable unsupported features.

#### Scenario: Switch account before admission
- **WHEN** a signed-in person is shown CGU, bootstrap or an admission-service error
- **THEN** the existing account control still exposes their identity and logout without querying protected business data
- **AND** signing in as another person clears the prior person's state and reevaluates their own admission

#### Scenario: Fresh platform and returning user
- **WHEN** a person enters Fred on a fresh platform
- **THEN** the existing CGU and bootstrap screens use manager state in that order
- **AND** completion leads into Fred's existing layout with home, account menu and authorized provisioning navigation
- **AND** reload preserves completed consent/bootstrap without repeating them

#### Scenario: Unsupported routes and background work
- **WHEN** an admitted person browses the implemented journey or opens a document, agent, marketplace or unsupported administration URL directly
- **THEN** unsupported navigation is absent and unsupported URLs return to home without mounting those features
- **AND** the application makes no control-plane, knowledge-flow or agent-runtime requests, including task polling, announcements and profile enrichment

#### Scenario: Admission becomes required or unavailable
- **WHEN** refreshed manager state requires a new consent version or cannot verify admission
- **THEN** admitted pages are gated until current admission is confirmed
- **AND** the UI does not fall back to Python consent, cached Python permissions or an alternative application
