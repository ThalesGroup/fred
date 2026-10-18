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

### Requirement: One Fred UI for the bounded first-user journey

This branch SHALL provide its first-user journey through Fred's existing application, layout, navigation, theme and shared screen components, including the admitted person's profile, preferences, legal pages and static release notes. It SHALL NOT expose a separate manager application or substitute a parallel navigation. CGU SHALL precede bootstrap, and admitted routes SHALL remain unavailable while admission state is loading or cannot be verified. Manager roles SHALL NOT be converted into control-plane permissions to enable unsupported features.

#### Scenario: Switch account before admission
- **WHEN** a signed-in person is shown CGU, bootstrap or an admission-service error
- **THEN** the existing account control still exposes their identity and logout without querying protected business data
- **AND** signing in as another person clears the prior person's state and reevaluates their own admission
- **AND** the admitted Profile action is absent until personal consent and platform bootstrap permit the protected journey

#### Scenario: Fresh platform and returning user
- **WHEN** a person enters Fred on a fresh platform
- **THEN** the existing CGU and bootstrap screens use manager state in that order
- **AND** completion leads into Fred's existing layout with home, account menu, own profile and authorized provisioning navigation
- **AND** reload preserves completed consent/bootstrap without repeating them

#### Scenario: Unsupported routes and background work
- **WHEN** an admitted person browses the implemented journey or opens an unsupported document, agent, marketplace or administration URL directly
- **THEN** unsupported navigation is absent and unsupported URLs return to home without mounting those features
- **AND** the application makes no control-plane, knowledge-flow or agent-runtime requests, including task polling, announcements and profile enrichment

#### Scenario: Admission becomes required or unavailable
- **WHEN** refreshed manager state requires a new consent version or cannot verify admission
- **THEN** admitted pages, including profile and its linked pages, are gated until current admission is confirmed
- **AND** the UI does not fall back to Python consent, cached Python permissions or an alternative application

### Requirement: Shared account pages require no organization membership

An admitted person SHALL open Fred's existing Profile entry and `/settings` page independently of organization or space membership. The page SHALL show the current authenticated identity and the platform roles reported by manager, retaining the existing interface-theme, light/dark/system, language and logout controls and the existing links to `/gcu`, `/gdpr` and `/release-notes`. Existing shared presentation and preference persistence SHALL be preserved. A configured contact-support link SHALL use the existing account-menu entry. This lot SHALL NOT expose photo upload/delete or the backend-published patch-note dialog.

#### Scenario: Platform owner without spaces
- **GIVEN** an admitted platform owner has no organization or space roles
- **WHEN** they open Profile from the existing account menu or navigate directly to `/settings`
- **THEN** the usual profile displays their own identity and manager platform roles, including `platform_owner`
- **AND** opening, reloading or changing a preference creates no membership, personal space or grant

#### Scenario: Roles are unavailable or belong to another account
- **WHEN** the manager role response is pending, fails, or the person changes accounts
- **THEN** the profile does not invent roles, substitute identity-provider roles, or display the previous person's identity or roles
- **AND** pending/error state is distinguishable from a successful response containing no platform roles

#### Scenario: Existing preferences and keyboard navigation
- **WHEN** an admitted person opens their profile using the keyboard and changes language, interface theme or display mode
- **THEN** the existing controls apply and persist their choices as usual
- **AND** Escape restores focus to the account-menu trigger, navigation closes the menu, and logout remains reachable before and after admission

#### Scenario: Legal pages and release notes
- **WHEN** the person follows the profile's CGU, privacy or release-notes link, or opens the corresponding URL directly after admission
- **THEN** the existing page reads its existing legal/release assets and provides its existing return navigation
- **AND** viewing accepted CGU does not write another acceptance or reopen bootstrap
- **AND** absent release text uses the existing unavailable-content presentation and never fabricated notes

#### Scenario: Ordinary imported person
- **WHEN** an imported person accepts their own CGU and opens Profile
- **THEN** the same pages are available with their own identity and platform roles, including a valid empty role list
- **AND** profile availability grants no platform-administration or content permission

### Requirement: Space hierarchy owned by OpenFGA
The canonical space tree SHALL be stored only as OpenFGA `parent` relations between spaces.
The SQL `space` table SHALL keep a space's identity, kind, name and personal owner,
never canonical parent or ancestor placement. A deletion receipt SHALL retain an
immutable `target_parent_id` snapshot solely for recovery, pending name reservation
and overlap checks after hierarchy links disappear; it SHALL NOT authorize access
or become a second canonical tree. Manager SHALL write a space's `parent` relation once, atomically with
its creation grants, and SHALL never change it. Only the authorized space-deletion
lifecycle SHALL remove hierarchy links, after persisting the affected space IDs
and their deletion operation. An organization SHALL have no parent, a team's parent
SHALL be an organization and a project's parent SHALL be a non-personal team.
Sibling names SHALL be unique, organization names SHALL be unique, and these rules
SHALL be enforced under the organization lock. Tuples left by an uncommitted creation
SHALL NOT be treated as spaces. Deletion bookkeeping SHALL NOT become a second
canonical hierarchy or store canonical roles.

#### Scenario: A project is created under a team
- **WHEN** a team administrator creates project P under team A
- **THEN** OpenFGA holds `space:A parent space:P` and the SQL `space` table holds no parent column
- **AND** a second project named P under A is refused, while P under another team succeeds

#### Scenario: A rolled-back creation leaves tuples
- **WHEN** a space's OpenFGA write succeeds and its SQL commit fails
- **THEN** listings, sibling-name checks and revocation checks ignore that id

#### Scenario: Hierarchy cleanup is interrupted
- **WHEN** a deletion activity removes a hierarchy link and then fails
- **THEN** the persisted deletion operation still identifies the affected retired space and organization
- **AND** retry completes cleanup without restoring grants or guessing scope from a missing link

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
`GET /me/spaces` SHALL return every active space where the caller holds a direct
role or a descending role through an ancestor, with its hierarchy path. `roles`
SHALL list the effective roles and `inherited_roles` the roles held only through
an ancestor. The listing SHALL be complete, without a server-side result limit.
Retired spaces SHALL be omitted even while their OpenFGA grants remain.

#### Scenario: Analyst of an organization
- **WHEN** Ana's only role is analyst on active TSN, which has active team A and project P
- **THEN** her listing contains TSN, A and P with role analyst
- **AND** analyst is inherited on A and P and direct on TSN

#### Scenario: Retired team retains grants during its delay
- **WHEN** team A and its project P are pending deletion
- **THEN** neither appears in Ana's workspace listing
- **AND** active siblings remain visible with unchanged permissions

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

### Requirement: Folder existence at mutation dispatch
Folder mutations SHALL recheck existence under the organization lock before SQL changes.
A folder deleted while the caller waits SHALL return not-found without a fabricated mutation success.

#### Scenario: Deletion wins over a waiting rename
- **WHEN** deletion commits while a folder rename waits for the organization lock
- **THEN** the waiter returns not-found and does not mutate a replacement or fabricate success

### Requirement: Personal space opens in the person's organization

Fred SHALL provide its existing personal-space navigation entry using manager
authority, with at most one personal space in the person's unique organization.
No separate creation button, organization selector or redesigned screen SHALL
be introduced. Personal-space identity SHALL come from its returned UUID and
personal owner, never a synthesized Python identifier.

#### Scenario: Priya opens her personal space after import
- **WHEN** Priya accepts the active terms after demo provisioning and has explicit personal-space creation eligibility and activates
  the existing personal-space entry in Demo
- **THEN** Fred opens her personal space, creating it if absent, and shows it
  through the existing selected-space detail and personal navigation presentation
- **AND** she retains navigation to fredlab with her admin, editor and analyst roles
- **AND** merely logging in, accepting terms or listing spaces creates no space

#### Scenario: Root without organization membership
- **WHEN** a platform-only root opens Home after bootstrap
- **THEN** the empty-membership view and authorized provisioning remain available
- **AND** no personal space, organization membership or content access is created

### Requirement: Repeated personal-space opening preserves current authority

`POST /fred-manager/v1/me/personal-space` SHALL require personal admission and
current read authority on the person's server-resolved organization. A supplied
organization identifier SHALL match that context. Creation SHALL additionally
require an explicit OpenFGA entitlement; organization membership alone SHALL NOT
provide it. It SHALL return 201 with a
new private space, or 200 with the same existing space when the caller currently
can read it. Reuse SHALL NOT write grants, repair revoked roles or replace an
inaccessible existing space. Creation SHALL retain the private member/editor
grants, no parent inheritance and the organization's revocation authority.
Concurrent opens SHALL create at most one committed space for that person and
organization. Dependency failure SHALL not be reported as successful opening.

#### Scenario: Repeat visit, reload and concurrent opening
- **WHEN** the same admitted person opens their personal space again, including
  two simultaneous requests within one organization
- **THEN** successful responses identify the same committed UUID
- **AND** only its first creation writes initial roles; reuse writes none

#### Scenario: Revoked roles remain revoked
- **WHEN** an administrator removes personal editor permission but leaves read access
- **THEN** reopening returns the space without restoring editor permission
- **WHEN** personal read access or organization read access is removed before the
  waiting opening request is authorized
- **THEN** opening is refused without restoring a role or creating a replacement

#### Scenario: Creation eligibility is absent or revoked
- **WHEN** a person without a personal space lacks its creation entitlement
- **THEN** opening cannot create the space or its initial roles
- **WHEN** the creation entitlement is revoked after a space exists
- **THEN** that revocation alone neither deletes the space nor changes its roles
- **AND** reuse still requires current organization and personal read authority

#### Scenario: Account changes during opening
- **WHEN** an opening request finishes after its originating account has changed
- **THEN** its completion does not select a space in the new context
- **AND** a failed opening exposes an error without fabricated success or silent retry

#### Scenario: Membership refresh is pending, failed or stale
- **WHEN** opening succeeds but the membership response has not confirmed the returned UUID
- **THEN** navigation retains the previous selection until the response confirms it
- **AND** failure or a response lacking the UUID shows an error and permits another explicit action

### Requirement: Memberships identify their managing organization

Each `/fred-manager/v1/me/spaces` item SHALL expose `organization_id` from its
canonical placement. Personal spaces SHALL retain no parent and a search path
containing only themselves. The organization field SHALL NOT imply inherited
permissions or an extension of personal content scope.

#### Scenario: Personal spaces remain private within each organization
- **WHEN** two people in distinct organizations list their spaces
- **THEN** each response is limited to the caller's organization and permissions
- **AND** neither personal path contains the organization or another space

### Requirement: Personal creation eligibility is explicit

The organization-only direct role `personal_space_creator` SHALL grant only
`can_create_personal_space`, without inheritance or content access. Organization
administrators SHALL manage it through existing role endpoints; bundles SHALL
use their existing role declarations. Its grant SHALL require direct organization
content membership, and the last such role SHALL not be removed while it remains.

#### Scenario: Eligibility is withheld or revoked
- **WHEN** an organization member lacks the creation role and has no personal space
- **THEN** opening a personal space is refused without writes
- **AND** removing that role from a person with an existing readable personal space does not prevent reuse

### Requirement: Personal eligibility model upgrades preserve existing data

When schema synchronization is enabled, startup SHALL upgrade only the exact
published predecessor model in the existing store and atomically publish its new
SQL model pointer. Ordinary loads and imports SHALL not publish models. Unknown
models SHALL be refused without resetting spaces or grants.

#### Scenario: Publication fails or overlaps
- **WHEN** two initializers run or SQL publication fails after the model POST
- **THEN** successful initializers converge on one pinned model
- **AND** failure leaves the previous SQL pointer usable for retry and preserves tuples

### Requirement: Authorized resource browsing in the provisioned space journey

After selecting a personal, team or project space, Fred SHALL expose its existing Resources navigation and read folders and document metadata from fred-manager using its generated contract. It SHALL retain the existing shared presentation and SHALL NOT mount control-plane, knowledge-flow, ingestion or conversation consumers. Organization context SHALL remain implicit and personal spaces SHALL use manager identifiers.

#### Scenario: Priya browses personal and collective resources
- **WHEN** admitted Priya opens her personal space or fredlab and then Resources
- **THEN** the UI lists only that space's root folders and documents
- **AND** opening a folder and using its breadcrumb or Back lists the corresponding parent contents
- **AND** an empty successful response shows the existing empty-folder message

#### Scenario: Document pagination
- **WHEN** a folder contains more documents than one UI page
- **THEN** Next and Previous traverse the name/id cursor pages without duplicates or omissions for unchanged data
- **AND** navigation to another folder or space resets pagination and never displays the previous scope's data
- **AND** the UI does not invent a total count or fetch the whole document collection

#### Scenario: Refusal, failure and revalidation
- **WHEN** current authorization or a list request fails, including when revisiting cached resources after revocation
- **THEN** the UI hides cached rows and distinguishes denied access from unavailable service and successful emptiness
- **AND** a retry reissues the current list requests

### Requirement: Folder filters belong to the authorized space

Manager folder and document listing SHALL enforce current personal admission, unique organization context and space read permission. A supplied parent/folder identifier SHALL belong to the requested space; a missing or foreign folder SHALL return 404 rather than a successful empty list. Admin and organization owner roles alone SHALL NOT grant content access; local members and effective editors/analysts SHALL retain their existing read semantics.

#### Scenario: Filter outside the requested space
- **WHEN** a reader supplies a nonexistent folder or a folder belonging to another space to either list endpoint
- **THEN** the endpoint returns 404 without exposing folder contents

#### Scenario: Direct API refusal and current grants
- **WHEN** a person without content read authority requests a list, including an organization's administrator or a reader whose grant has been revoked
- **THEN** the endpoint refuses the request and returns no rows
- **AND** an authorized content reader or editor still obtains only the requested space and folder's metadata

### Requirement: Authorized folder creation in Resources

The Resources journey SHALL let an admitted person with effective write permission
create a folder at the root or inside a folder of the current personal, team or
project space using fred-manager only. Creation SHALL make no Temporal call; its governance router SHALL require no ingestion client.
The server MUST enforce the person's unique organization and current write authority;
administration, membership or analyst rights alone SHALL NOT grant content writes.

#### Scenario: Create and browse
- **WHEN** an authorized editor creates a folder in the current location
- **THEN** the folder is persisted there and appears in the refreshed first page
- **AND** the user can open it and return using the existing breadcrumb

#### Scenario: Revocation and isolation
- **WHEN** a caller lacks write permission, loses it before a waiting write is admitted, or targets another person's private space or another organization
- **THEN** creation is refused without inserting a folder

#### Scenario: Repeated submission and navigation
- **WHEN** the user submits repeatedly while creation is pending or navigates away
- **THEN** that dialog issues at most one concurrent create request and its completion does not change the new location

### Requirement: Folder creation validates location and name

Creation SHALL trim surrounding whitespace and accept a nonempty single-segment name
of at most 255 Unicode scalar values, without slash, backslash or control characters.
It SHALL preserve the existing 15-level folder ceiling and sibling name uniqueness.
Invalid names/depth SHALL return 422, missing parents 404, foreign-space parents 400,
and duplicate sibling names 409. Refused creations MUST NOT change stored content.

#### Scenario: Invalid name or excessive nesting
- **WHEN** the requested name is invalid or the new folder would exceed 15 levels
- **THEN** the server returns 422 and the UI keeps the dialog open with an error

#### Scenario: Duplicate or invalid parent
- **WHEN** a caller creates an existing sibling name or supplies a missing or foreign-space parent
- **THEN** the server returns the corresponding conflict or location error
- **AND** the UI preserves the entered name and lets the user correct or cancel

### Requirement: Explicit technical authority requests space deletion
Manager SHALL expose `DELETE /spaces/{id}` for organizations, ordinary teams and
projects and `GET /deletions/{operation_id}` for deletion status. Both SHALL
require authenticated admission and a current OpenFGA `can_delete_space` platform
permission, granted only by platform ownership. They SHALL NOT grant content read.
Organization ownership or local administration alone SHALL NOT authorize them.
A deletion SHALL include the complete committed subtree and an organization's
personal spaces. A standalone personal-space deletion SHALL be refused.

#### Scenario: Technical deletion without content access
- **WHEN** an admitted platform owner requests deletion of an organization they cannot read
- **THEN** its deletion is accepted without requiring or granting a content role
- **AND** its teams, projects and personal spaces are included, while other organizations are untouched

#### Scenario: Local administrator cannot escalate deletion authority
- **WHEN** a caller with only organization owner or space admin requests deletion or its receipt
- **THEN** the request is forbidden and no lifecycle state or role changes

#### Scenario: Last administrator and role revocations remain separate
- **WHEN** an authorized platform owner deletes a space containing its last administrator
- **THEN** the space can be retired and its roles cleaned at expiry
- **AND** ordinary role revocations on active spaces retain their existing last-admin, dependency and personal-space rules

### Requirement: Deletion acceptance is durable and idempotent
Acceptance SHALL atomically persist an operation and retire every included space,
returning 202 with a stable operation ID, target, status, request time and scheduled
deletion time. It SHALL NOT depend on dispatching a Temporal request during the
HTTP transaction. Repeating DELETE for the same UUID SHALL return the existing
operation and original due time, including after cleanup (200 when completed).
Overlapping ancestor/descendant operations SHALL be rejected with 409 without
partial retirement. An unknown target SHALL return 404 after authorization.

#### Scenario: API response is lost
- **WHEN** acceptance commits but the connection drops before its response
- **THEN** retry returns the same operation and due time with no duplicate cleanup

#### Scenario: Temporal is temporarily unavailable
- **WHEN** lifecycle is enabled and a deletion is accepted while Temporal is unreachable
- **THEN** the durable operation remains queued and is processed after recovery
- **AND** no request is lost between SQL commit and Temporal dispatch

#### Scenario: Parent deletion overlaps a pending child
- **WHEN** a project is already pending deletion and its team's deletion is requested
- **THEN** the second request returns 409 and leaves the team active

#### Scenario: Pending child already lost its hierarchy link
- **WHEN** a project's parent tuple was removed but its cleanup has not completed
- **THEN** deleting its team still returns 409 using durable operation placement
- **AND** creating or importing the same project name in that team remains refused

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

### Requirement: Policies validate and freeze the deletion deadline
Manager SHALL load a versioned space-deletion policy from
`policies.purge_catalog_path`, with `default`, ordered `rules`, `match` and `action`.
Supported actions SHALL be `mode` (`deferred_delete` or `immediate_delete`) and
nonnegative ISO-8601 `retention` using weeks, days, hours, minutes and seconds.
Rules SHALL match space kind and/or UUID, prefer the most defined criteria and
use file order for equal specificity. Defaults SHALL be deferred deletion and P7D.
Unknown fields, invalid durations, empty match values, invalid kinds/UUIDs and overflows
SHALL fail configuration validation. Unsupported conversation policies SHALL NOT
be silently accepted. The accepted operation SHALL freeze its resolved policy
and due time; a later configuration change SHALL NOT rewrite it.

#### Scenario: Immediate mode still executes through the worker
- **WHEN** an immediate policy matches an accepted request
- **THEN** its due time equals its request time and the API still returns an asynchronous receipt

#### Scenario: Worker restarts after policy change
- **WHEN** a P7D request remains pending and the catalog changes to P1D
- **THEN** its original deadline is retained and only new requests use P1D

#### Scenario: Unsupported setting or invalid duration
- **WHEN** the space catalog supplies `cancel_on_rejoin`, a negative duration, calendar months, or a value that overflows the due timestamp
- **THEN** validation refuses it rather than starting with an ineffective or wrapped policy

### Requirement: Temporal owns recoverable bounded cleanup
A separately runnable Rust Temporal worker SHALL periodically process due durable
operations on its own queue and schedule. API and worker SHALL share configuration
conventions, explicit timeouts and a validated lifecycle enable switch. Omitted
lifecycle configuration SHALL disable new deletion requests (503 before mutation).
Disabled workers SHALL execute no cleanup. Repeated worker startup SHALL NOT
duplicate schedules. Schedule reconciliation SHALL preserve manager ownership and
avoid collisions with control-plane/ingestion. No cleanup SHALL run before due time;
sweep cadence, backlog and outages can delay completion. Work and retries SHALL
be bounded per candidate, and a failing candidate SHALL NOT starve other operations.

#### Scenario: Restart and retry
- **WHEN** the worker stops midway through cleanup and restarts after the deadline
- **THEN** it resumes persisted unfinished work without an end-user token or duplicate schedule

#### Scenario: One failing candidate among due operations
- **WHEN** one operation exhausts its bounded activity retries
- **THEN** its incomplete status is persisted and other eligible operations can progress

#### Scenario: Shutdown while an activity waits for SQL
- **WHEN** SIGTERM reaches a worker with an activity waiting for a SQL lock
- **THEN** finite shutdown grace, local cancellation and server-side SQL limits release the activity and its wait
- **AND** restarting resumes its durable incomplete operation

#### Scenario: Disabled lifecycle
- **WHEN** lifecycle is disabled
- **THEN** new deletion requests return 503 without retirement, the owned schedule is paused when reachable, and no worker cleanup starts
- **AND** authorized status reads and retries returning an existing receipt remain available

#### Scenario: Activation during rolling deployment
- **WHEN** an older API replica or provisioning producer can still access the installation
- **THEN** lifecycle acceptance and cleanup remain disabled until every producer supports retirement
- **AND** worker availability alone is insufficient to activate deletion safely

### Requirement: Completion proves cleanup of implemented stores only
Manager SHALL remove folder trees, space rows and all OpenFGA references for the
accepted scope, with bounded filtered tuple reads/writes and descendant-first
ordering. Rows identifying cleanup work SHALL survive until their required
external references are verified absent. Ambiguous acknowledgments SHALL be
resolved by rereading state, never by assuming rollback or marking success.
Accounts, consent, platform grants and unrelated spaces SHALL remain unchanged.
Scopes with any document rows SHALL return 409 before acceptance; unexpected
content found later SHALL block completion and remain visible. No remote content
store SHALL be reported cleaned by this implementation.

#### Scenario: Document-bearing scope
- **WHEN** an otherwise authorized request includes a descendant with document metadata
- **THEN** it returns 409 and creates no deletion operation or retirement marker

#### Scenario: OpenFGA committed but acknowledgment was lost
- **WHEN** a tuple deletion times out after taking effect
- **THEN** retry rereads present tuples, obtains fresh authorization guards and converges
- **AND** SQL identifying the remaining work is retained until references are verified absent

#### Scenario: Large and unrelated scopes
- **WHEN** the target has more than one tuple/folder batch and another organization has many unrelated tuples
- **THEN** every target item is removed with bounded filtered requests and no pagination omission
- **AND** unrelated store cardinality does not add client-side full-store scans

### Requirement: Deletion progress and audit remain truthful
The status API SHALL distinguish queued, running, retrying, blocked and completed
operations. Completion SHALL require both implemented stores to be verified clean;
partial failure SHALL expose a safe actionable code and retain retry context.
Minimal receipts SHALL outlive their target and contain no bearer, content, names
or canonical role copies. Request acceptance and verified completion SHALL emit
structured audit events with actor/operation/scope identifiers. Worker application
logs SHALL identify the worker service role and sanitize dependency failures.

#### Scenario: Partial cleanup is inspected
- **WHEN** some effects succeeded but a later cleanup step failed
- **THEN** the API reports an incomplete operation with preserved due time and safe error code
- **AND** neither receipt nor audit claims complete erasure or an unverified exact tuple-deletion count

#### Scenario: Completed target is absent
- **WHEN** an authorized operator queries the receipt after SQL target removal
- **THEN** the completed receipt remains readable without resolving deleted hierarchy links

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
