# Fred Manager Provisioning

## Purpose

Provision Fred identities and organization/team/project spaces through authenticated
Rust CLI and HTTP ZIP import, with the complete assignable role catalog and enforceable permissions.

## Requirements

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
and name, rejecting incompatible-kind collisions. Personal spaces SHALL NOT take
part in name resolution. Replay SHALL reuse committed identities/spaces, repair
missing requested grants and preserve undeclared existing grants. A changed name
SHALL identify a different space. Every mutation SHALL check the caller's current
authority while serialized with relevant revocations. Parent content grants SHALL
precede child roles and preserve the parent/child invariant even across errors and
retries. Partial dependency failure SHALL report failure without claiming
distributed rollback or deleting created users. Success SHALL mean all declared
state was reconciled.

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

### Requirement: Explicit hierarchy during ZIP reconciliation

Import SHALL resolve organizations by root name, teams by organization/name and
projects by team/name, reading children from OpenFGA after the organization lock.
Bundle references SHALL only resolve declarations within that bundle. Existing
committed target IDs and undeclared grants SHALL be preserved on replay. Names
shared across different parents SHALL remain distinct; incompatible-kind
collisions SHALL be refused. A new space's `parent` relation SHALL be published
with that organization's grants. Current root, parent-membership and
authority-recheck protections SHALL apply at every level.

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
The first-person UI SHALL present terms before the existing secret-gated root bootstrap. It SHALL use manager state and generated manager calls only. Bootstrap SHALL grant only platform ownership, preserving exclusive claimant recovery and permanent completion. It SHALL NOT create an organization or enroll the root in one. Errors and retries SHALL remain explicit, and an unavailable status service SHALL NOT admit the UI.

#### Scenario: Fresh platform root
- **WHEN** a person accepts terms and supplies the valid deployment secret on a fresh platform
- **THEN** they become platform owner and can open provisioning
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

### Requirement: Space hierarchy owned by OpenFGA
The space tree SHALL be stored only as OpenFGA `parent` relations between spaces.
SQL SHALL keep a space's identity, kind, name and personal owner, never its parent
or ancestors. Manager SHALL write a space's `parent` relation once, atomically with
its creation grants, and SHALL never change or delete it. An organization SHALL have
no parent, a team's parent SHALL be an organization and a project's parent SHALL be a
non-personal team. Sibling names SHALL be unique, organization names SHALL be unique,
and these rules SHALL be enforced under the organization lock. Tuples left by an
uncommitted creation SHALL NOT be treated as spaces.

#### Scenario: A project is created under a team
- **WHEN** a team administrator creates project P under team A
- **THEN** OpenFGA holds `space:A parent space:P` and SQL holds no parent column
- **AND** a second project named P under A is refused, while P under another team succeeds

#### Scenario: A rolled-back creation leaves tuples
- **WHEN** a space's OpenFGA write succeeds and its SQL commit fails
- **THEN** listings, sibling-name checks and revocation checks ignore that id

### Requirement: Descending roles
Editor, admin and analyst roles SHALL apply to the space where they are granted and
to all its descendants. Member SHALL apply only to its own space. Inheritance SHALL
be evaluated by the OpenFGA model; manager SHALL NOT copy inherited grants as tuples.
A project SHALL NOT be excluded from its ancestors' descending roles.

#### Scenario: Organization roles reach projects
- **WHEN** Bob is editor of organization TSN, Ana analyst of TSN and Max member of TSN
- **THEN** Bob reads and writes every team and project of TSN
- **AND** Ana reads them and holds every evaluation permission there
- **AND** Max reads TSN only

#### Scenario: Team administration reaches projects without content
- **WHEN** Claire is admin of team A only
- **THEN** she manages A and its projects and reads none of their content

### Requirement: Personal spaces inherit nothing
A personal space SHALL have no `parent` relation. An `organization` relation, used by
no permission, SHALL record the organization that manages it. Roles held on that
organization SHALL grant nothing in the personal space; its organization's admins
SHALL still be able to remove its owner. A person SHALL hold at most one personal
space per organization.

#### Scenario: Organization editor and Alice's space
- **WHEN** Bob is editor of TSN and Alice owns a personal space in TSN
- **THEN** Bob can neither read nor write Alice's personal space
- **AND** an admin of TSN can revoke Alice's roles on it

### Requirement: Inherited memberships are listed
`GET /me/spaces` SHALL return every space where the caller holds a direct role or a
descending role through an ancestor, with its hierarchy path. `roles` SHALL list
the effective roles and `inherited_roles` the roles held only through an ancestor.
The listing SHALL be complete, without a server-side result limit.

#### Scenario: Analyst of an organization
- **WHEN** Ana's only role is analyst on TSN, which has team A and project P
- **THEN** her listing contains TSN, A and P with role analyst
- **AND** analyst is inherited on A and P and direct on TSN

### Requirement: Scope follows ancestors with optional levels
`POST /authorize/scope` SHALL check the caller's read permission on the requested
space, then return that space and its ancestors from the organization down. A
personal space's scope SHALL be itself. An optional `levels` list of
`organization`, `team` and `project` SHALL keep only spaces of those kinds; it SHALL
never add a space. Descendants SHALL never be part of a scope.

#### Scenario: Project scope narrowed to the project
- **WHEN** Bob requests the scope of project P with levels `[project]`
- **THEN** the response contains P only
- **AND** without levels it contains TSN, A and P in that order

### Requirement: Guarded role publication from an empty installation

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

Startup SHALL bind an existing published store and model, or initialize an entirely
empty installation. Any other state SHALL fail startup and requires a data reset;
manager SHALL NOT convert existing authorization data. Published routing metadata
SHALL pin the active store and model IDs, without moving roles into SQL. Local SQL
mutations SHALL hold their organization lock through guarded authorization and
commit. External Keycloak/Temporal operations SHALL be authorized at dispatch;
timeout or revocation SHALL NOT be described as cancellation of remote effects.

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

#### Scenario: Existing state without a publication
- **WHEN** manager starts against spaces, tuples or bootstrap state without a
  published binding, or against a binding whose model differs
- **THEN** startup fails without writing and names the reset as the remedy

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
