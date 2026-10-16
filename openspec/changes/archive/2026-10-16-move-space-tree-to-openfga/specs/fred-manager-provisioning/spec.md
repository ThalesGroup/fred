## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Complete scoped role model

The system SHALL support cumulative space roles `member`, `editor`, `admin` and
`analyst` on organizations, teams and projects. Member, editor and analyst SHALL
grant content read; only editor SHALL grant generic content write; only admin SHALL
grant governance. Editor, admin and analyst SHALL also apply to every descendant
space; member SHALL NOT. Analyst SHALL grant evaluation execution,
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

## REMOVED Requirements

### Requirement: Role publication survives unknown remote outcomes
**Reason**: The offline cutover it requires cannot recreate `parent` tuples once SQL no longer stores the tree.
**Migration**: Replaced by "Guarded role publication from an empty installation"; existing manager data is reset, not converted.
