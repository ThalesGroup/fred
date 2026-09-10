## Purpose

Defines configuration-based application registration and typed, team-scoped
application authorization independently of agent capabilities and downstream
resource permissions. Global resource deactivation and deletion are a future
cross-type gap, not functionality delivered by this change.

## ADDED Requirements

### Requirement: Applications use a distinct authorization resource

Fred SHALL authorize applications against `app:<app_id>`. The shared catalog
and administration wire identifier SHALL remain `app__<app_id>` with
`kind="app"`. Writers SHALL resolve a validated catalog entry to its typed
resource without repairing invalid ids into different application ids.
Runtime capability manifests SHALL NOT gain an `app` kind.

#### Scenario: Catalog id maps to an app object

- **GIVEN** a registered app with id `example-app`
- **WHEN** its `app__example-app` administration entry is resolved
- **THEN** authorization reads and writes target `app:example-app`, not
  `capability:app__example-app`

#### Scenario: A capability check cannot stand in for an app check

- **GIVEN** a first-party backend uses the ReBAC SDK
- **WHEN** it calls `check_team_capability` with `app__example-app`
- **THEN** the call is refused and the caller must use
  `check_application_access` with the raw app id

### Requirement: Resource types isolate tuples and enablement caches

Application and capability resources sharing a raw id SHALL remain distinct
in permission checks, direct relation reads, tuple writes, and enablement
caches. Cache keys and invalidation markers SHALL include the resource type
as well as its id. Mutating an app SHALL NOT mutate or invalidate the
same-id capability's relations or cache entry.

Administration caches SHALL NOT determine application admission. Local
invalidation SHALL prevent an older fill from becoming reusable after an
overlapping mutation, and attempted writes SHALL invalidate their typed cache
even when only part of the mutation succeeds. These process-local caches
SHALL NOT be represented as cross-replica synchronization.

#### Scenario: Same-id resources retain separate cached grants

- **GIVEN** `app:shared` grants one team access and `capability:shared` grants
  a different team access
- **WHEN** Fred builds both administration rows and then reads both again
- **THEN** each row contains only its own typed resource's grants
- **AND** repeated reads reuse separate cache entries without another relation read

#### Scenario: An app grant does not grant the same-id capability

- **GIVEN** `app:shared` and `capability:shared` have organization anchors
  and neither has a team grant or default-on inheritance
- **WHEN** a team receives an explicit grant on `app:shared`
- **THEN** that team can use the app but cannot use `capability:shared`
- **AND** another team without an app grant cannot use the app

#### Scenario: App mutation refreshes only the app cache entry

- **GIVEN** both `app:shared` and `capability:shared` have cached relations
- **WHEN** an administrator changes the app's team entitlement
- **THEN** the next app administration read fetches its updated relations
- **AND** the same-id capability's tuples and cached result remain unchanged

#### Scenario: A local cache fill overlaps a mutation

- **GIVEN** a relation read is in flight on one replica
- **WHEN** a mutation invalidates that typed resource before the fill completes
- **THEN** the old fill is not reusable on the next administration read

#### Scenario: An entitlement mutation partially fails

- **GIVEN** an administration cache contains an app's relations
- **WHEN** an entitlement change writes one relation and then fails
- **THEN** the attempted mutation invalidates the app cache
- **AND** the operation does not report complete success

### Requirement: Application admission requires membership and entitlement

With ReBAC enabled, application admission SHALL require both the user's
`can_use_team_applications` on the selected collaborative team and that team's
`can_use` on the application. The user permission SHALL be checked first.
Public team visibility and platform administration SHALL NOT substitute for
team membership.

#### Scenario: A member of an entitled team is admitted

- **GIVEN** a user holds a team role and the team may use the app
- **WHEN** the backend checks application access
- **THEN** the membership check and the team-subject app check both succeed

#### Scenario: A platform administrator is not a member

- **GIVEN** a platform administrator holds no role on an app-enabled team
- **WHEN** the backend checks application access
- **THEN** membership is denied before querying the app entitlement

#### Scenario: Membership alone is insufficient

- **GIVEN** the user is a member but the team has no effective app grant
- **WHEN** the backend checks application access
- **THEN** access is denied

### Requirement: Explicit denial overrides application enablement

The app model SHALL use `(enabled or inherited) but not disabled` for
`can_use`, without an additional app-wide active marker, with `inherited` derived from `team from default_on`. `enabled`
and `disabled` SHALL accept team subjects; `default_on` and `organization`
SHALL accept organization subjects. Registration or an organization anchor
alone SHALL NOT grant access.

#### Scenario: Default-on admits a collaborative team

- **GIVEN** a registered app is default-on for the organization and the team is not disabled
- **WHEN** Fred checks the team-subject app permission with its organization context
- **THEN** the team inherits `can_use`

#### Scenario: A deny wins over both grant sources

- **GIVEN** a team is explicitly enabled, the app is default-on, and the team
  also has a `disabled` relation
- **WHEN** Fred checks `can_use`
- **THEN** the result is denied

#### Scenario: Registration is not enablement

- **GIVEN** a registered app has only its structural organization anchor
- **WHEN** a team with no grant or default-on inheritance checks app access
- **THEN** the team is not entitled

### Requirement: V1 applications exclude personal spaces

App discovery SHALL return no applications for personal spaces. Every
first-party SDK authorization check SHALL reject personal spaces before
contacting OpenFGA. Administration SHALL reject new personal-team app grants
and personal-class controls, while retaining cleanup of stale personal tuples.

#### Scenario: Default-on does not admit a personal space

- **GIVEN** an application is default-on
- **WHEN** a personal team requests its application catalog
- **THEN** the catalog is empty
- **AND** a direct first-party SDK check for that space is refused locally

#### Scenario: A stale personal grant can be removed but not recreated

- **GIVEN** a registered app has a stale personal-team entitlement tuple
- **WHEN** an authorized administrator removes it
- **THEN** cleanup remains available
- **AND** attempting to grant the app to that personal team is rejected

### Requirement: Application administration remains independent of agents

App `can_manage` SHALL derive from `platform_admin from organization`.
Existing platform-admin capability administration routes SHALL remain the
app enablement writers. App operations SHALL NOT enter agent dependency,
impact, health, suspension, revival, settings, or model-binding paths.

#### Scenario: Changing an app grant does not change managed agents

- **GIVEN** a team has managed agents and an application entry
- **WHEN** an authorized administrator enables or disables the app
- **THEN** the app relations change without modifying agent configuration,
  suspension, or dependencies

#### Scenario: App administration does not become an agent capability

- **GIVEN** the shared admin catalog contains an app row
- **WHEN** Fred reports that row
- **THEN** agent impact and reasoning fields are empty and the app is not
  projected as a runtime capability manifest

### Requirement: App backends authenticate independently of the frame

The Fred host SHALL retain the user's raw bearer outside frame code and
forward it only on the proxied service-request leg. The app backend SHALL
validate the incoming bearer before checking entitlement. The gateway SHALL
NOT be treated as the authorization authority.

#### Scenario: A first-party app receives the wrong audience

- **GIVEN** an incoming JWT does not carry the app backend's configured C3 audience
- **WHEN** that backend authenticates the request
- **THEN** authentication is refused even if the user would have an app grant

#### Scenario: The frame requests an authenticated operation

- **GIVEN** a resolved app frame requests a relative service operation
- **WHEN** the host sends the team-scoped proxied request
- **THEN** the backend receives the caller's bearer without the host returning
  that raw bearer to the frame

### Requirement: First-party authorization is narrow and fail-closed

An operator-admitted first-party backend SHALL construct and reuse one
process-lifetime SDK using `rebac_sdk_factory`, then close it at shutdown.
The factory SHALL require C3, enabled user/M2M/OpenFGA authentication,
non-ownership of the store and model, a process KPI writer, and an explicit
1–30,000 ms OpenFGA timeout. It SHALL initialize the configured store connection
at startup and SHALL NOT substitute a permissive engine on failure.

The SDK SHALL expose named authorization checks rather than a tuple writer,
raw client, or general query interface. An arm's-length backend SHALL instead
require its own app id in the team catalog obtained with the caller's bearer.

#### Scenario: Unsafe first-party configuration is refused

- **GIVEN** store creation or schema synchronization is enabled, ReBAC is
  disabled, or the timeout is absent or outside the allowed range
- **WHEN** a first-party backend constructs its SDK
- **THEN** construction fails rather than weakening authorization

#### Scenario: OpenFGA startup cannot complete

- **GIVEN** OpenFGA credentials are invalid, the store is absent, or the
  configured endpoint cannot be reached
- **WHEN** the SDK initializes
- **THEN** startup fails without granting access through a fallback engine

#### Scenario: An arm's-length backend is not entitled

- **GIVEN** a caller's authenticated team catalog omits the app id
- **WHEN** an arm's-length backend checks entitlement
- **THEN** it refuses access

### Requirement: Configuration registration does not create a lifecycle authority

An enabled configured application SHALL appear in the registered catalog.
Configuration registration SHALL NOT write authorization tuples or grant team
access. Startup seeding SHALL skip the admin-gated entry. Authorized entitlement
mutations SHALL establish the organization anchor on the dedicated app type,
without a lifecycle database, adoption step or global active marker.

A catalog-hidden or removed entry SHALL NOT trigger bulk permission cleanup
or be represented as global authorization revocation. Existing permissions
SHALL remain outside configuration-removal lifecycle management. No new
Deactivate/Delete UI, command or lifecycle API SHALL be introduced.

#### Scenario: An enabled application is registered

- **GIVEN** the application feature and ReBAC are enabled
- **WHEN** an enabled application entry is loaded and registration seeding runs
- **THEN** the catalog entry maps to its app authorization object
- **AND** startup seeding writes no app tuples
- **AND** existing authorized entitlement controls establish the typed anchor without lifecycle adoption

#### Scenario: A configured entry is hidden from the catalog

- **GIVEN** an application has existing team permissions
- **WHEN** its configuration entry is set to `enabled: false`
- **THEN** it is absent from team discovery
- **AND** this does not guarantee denial by a directly reachable first-party backend
- **AND** supported revocation remains available while new grants are refused

#### Scenario: An application entry is removed and re-added

- **GIVEN** stored authorization relations exist for an application
- **WHEN** its entry is removed from configuration and later re-added
- **THEN** removal does not automatically delete those relations
- **AND** re-registration does not promise a fresh permission generation

### Requirement: App admission uses fresh authorization reads

Discovery and first-party app checks SHALL request the authorization engine's
higher-consistency path. An administration cache SHALL NOT supply a cached
allow decision in place of those checks. This does not cancel previously
admitted work or introduce a distributed write transaction.

#### Scenario: A team grant is revoked or denied

- **GIVEN** a team could use an application
- **WHEN** its entitlement changes and another app check is made
- **THEN** the check requests higher consistency from the authorization engine
- **AND** it does not reuse an administration-cache allow result

### Requirement: Touched operational logs exclude sensitive data

Touched authorization, cleanup, seeding and database-construction log sinks
SHALL exclude secrets, secret names, system identifiers, connection details
and raw provider exceptions. Generic failure status SHALL remain observable.
This requirement covers the changed sinks rather than asserting a repository-wide audit.

#### Scenario: A database constructor fails with sensitive details

- **GIVEN** a dependency exception contains connection details or a chained sensitive error
- **WHEN** the database-construction failure is logged
- **THEN** the log contains only generic failure status without the raw traceback
- **AND** the operation still fails

#### Scenario: An authorization check denies a request

- **WHEN** a touched authorization check logs denial
- **THEN** no subject, actor or resource identifier is emitted into the operational log

### Requirement: The application feature flag remains an availability control

The disabled application feature gate SHALL withdraw normal browser,
catalog, and app-administration paths while retaining dormant grants.
The first-party SDK SHALL continue evaluating ReBAC independently of catalog
and feature-flag settings. The deployment-wide feature flag SHALL NOT be
represented as per-app global authorization revocation.

#### Scenario: Revocation defeats default-on access

- **GIVEN** an app is default-on for the organization
- **WHEN** an authorized administrator disables it for one collaborative team
- **THEN** that team's app check is denied despite default-on inheritance

#### Scenario: Disabled ReBAC remains confined to the existing permissive mode

- **GIVEN** the application feature is enabled and the platform runs with ReBAC disabled
- **WHEN** a collaborative team requests its application catalog
- **THEN** registered enabled apps are returned under the existing development behavior
- **AND** this configuration cannot construct a first-party SDK

### Requirement: App access does not widen downstream resource authority

An app grant SHALL NOT substitute for agent capability enablement, agent
instance permissions, Knowledge Flow object permissions, or a verified
Workspace execution binding. Applications SHALL access another backend's
data through its API and satisfy that backend's authorization. This requirement
does not implement the separately planned Workspace contract.

#### Scenario: An app user cannot read a forbidden corpus document

- **GIVEN** a user may use the app but lacks access to a selected corpus document
- **WHEN** the app requests it through Knowledge Flow on the user's behalf
- **THEN** the app grant supplies no override of Knowledge Flow's denial

#### Scenario: An app grant is not a delegated Workspace credential

- **GIVEN** an app grant and a human bearer or the app's own M2M identity
- **WHEN** evaluating admission under the planned Workspace agent-write contract
- **THEN** neither establishes the required exact runtime identity and verified
  execution binding; that separate authorization must still be satisfied

### Requirement: Cutover refuses semantic legacy application grants

Operators using the branch's no-migration cutover SHALL fence and drain old
app writers, verify absence of semantic legacy grants, deploy and verify the
app-aware model and pinned readers, and recheck legacy state before reopening
writes. Any legacy `enabled`, `disabled`, `default_on`, `personal_on`, or
`personal_disabled` app relation SHALL block that cutover pending a separate
migration design. App checks SHALL NOT fall back to legacy capability grants.
This is an operational precondition, not an automated migration in this change.

#### Scenario: A legacy deny is present

- **GIVEN** preflight finds a `disabled` tuple on `capability:app__example-app`
- **WHEN** an operator evaluates the no-migration cutover
- **THEN** rollout stops rather than discarding that semantic state

#### Scenario: An old grant cannot override a new denial

- **GIVEN** a new app check is denied and a legacy capability grant still exists
- **WHEN** a new reader evaluates the request
- **THEN** it does not consult the old capability grant as an access fallback

#### Scenario: A late old write prevents reopening administration

- **GIVEN** the new model and readers are deployed with the writer fence still closed
- **WHEN** the post-drain legacy check finds a semantic app tuple
- **THEN** administration remains fenced pending a separate migration decision

## Deferred gap

Global Deactivate/Activate/Delete semantics require a future shared design for
all or most applicable ReBAC types. This change does not select that mechanism
or implement automatic permission cleanup. The scope, ownership, state authority,
recovery, cache coherence and rollout questions are recorded in the
[design](../../design.md#deferred-gap--shared-resource-lifecycle).
