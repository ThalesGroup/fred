## MODIFIED Requirements

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

## ADDED Requirements

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
ingestion dispatch, provisioning reuse and personal-space reuse in that scope.
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
