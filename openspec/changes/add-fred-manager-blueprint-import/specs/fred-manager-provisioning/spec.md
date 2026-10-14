## MODIFIED Requirements

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

## ADDED Requirements

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
ID or early success. Errors SHALL retain safe phase/count information, use Fred's
`detail` envelope and never expose credentials, input bodies or upstream bodies.
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
