## Purpose

Defines the separation of the calling workload from the person a request acts
for, the standing requirement applied to every authorization decision, and the
removal of role-based access that names no person.

## ADDED Requirements

### Requirement: A request has a caller and a subject

Every authenticated request SHALL carry a caller (the identity authenticated by the bearer)
and, when present, a subject (the authenticated or asserted person). Authorization
decisions SHALL use the subject. A service-role check SHALL evaluate the caller
only. An asserted person SHALL NOT satisfy the service-role predicate, and a true
caller predicate SHALL NOT grant the subject access to a delegated operation.

#### Scenario: Asserted person never satisfies a service-role check

- **GIVEN** a service caller holding the service role and a subject built from a grant
- **WHEN** their identities and permission for a delegated operation are evaluated
- **THEN** the caller satisfies the service-role predicate, the asserted subject
  does not, and access still requires the subject's standing and permission

### Requirement: Standing is required on every decision

For a person subject, the authorization engine SHALL require the person's
`organization#active` relation on every check, batch check and list lookup, and
SHALL produce a distinct authorization denial when standing is absent or its check
cannot run. That denial SHALL survive list, batch and filtering paths as an
authorization failure, never a successful empty result. A delegated run receiving
it SHALL end with `authority_lost` and cancel its children.

#### Scenario: Direct grant without standing

- **GIVEN** a person who owns a tag directly but holds no `active` relation
- **WHEN** their run reads the tag
- **THEN** the read is denied

#### Scenario: List lookup without standing

- **GIVEN** a person without `active`
- **WHEN** resources are listed for them
- **THEN** the receiver returns an authorization failure, the run ends with
  `authority_lost`, and its children are cancelled

#### Scenario: Standing failure through batch filtering

- **GIVEN** a run whose person loses standing
- **WHEN** its next call filters search results through permission checks
- **THEN** the standing failure is preserved as an authorization failure and ends
  the run, rather than removing all results and reporting success

#### Scenario: Active person with no matching accessible resources

- **GIVEN** a person with standing and no accessible resources matching a listing
- **WHEN** resources are listed for them
- **THEN** an ordinary successful empty list is permitted without ending the run

#### Scenario: Standing check unavailable

- **WHEN** the standing check cannot be evaluated
- **THEN** the receiver returns the bounded standing-unavailable failure (HTTP
  503), without upstream details, and no data is returned

### Requirement: Standing is a block list owned by the platform

Every authenticated person SHALL be in good standing unless the platform has
suspended them. The authorization model SHALL derive a person's
`organization#active` from one default standing entry covering every person,
excluding each person who holds `organization#suspended`. The platform SHALL be
the only source of standing: no identity-provider listing, account status or
administration right SHALL be read to decide or change it. A service identity
evaluated as a person subject SHALL be in good standing under the same rule, and
its access SHALL still require its own relations. When the default standing entry
is absent, no person SHALL be in good standing.

#### Scenario: Person never suspended

- **GIVEN** the default standing entry exists and a person holds no suspension
- **WHEN** an authorization decision is made for that person
- **THEN** standing holds without any per-person provisioning, and the decision
  depends on the person's permission on the object

#### Scenario: Suspended person

- **GIVEN** a person who holds `organization#suspended`
- **WHEN** a check, batch check or list lookup is made for them
- **THEN** standing does not hold and the typed standing denial is returned,
  whatever other relations the person holds

#### Scenario: Service identity checked as a person

- **GIVEN** a service identity, such as a knowledge-base pod account, evaluated as
  the subject of a decision
- **WHEN** its standing is checked
- **THEN** it is in good standing, and access still requires its own relations on
  the object

#### Scenario: Default standing entry absent

- **GIVEN** a store without the default standing entry
- **WHEN** a decision is made for any person
- **THEN** standing does not hold and access is denied

### Requirement: Identity-provider account changes do not change standing

Creating, disabling, re-enabling or deleting an account in the identity provider
SHALL NOT change the person's standing. When the account is disabled or deleted
there, the person's interactive access SHALL end when their current token expires.
Delegated runs, background tasks and scheduled runs acting for that person SHALL
keep their authorization, subject to the person's standing and permissions, until
the person is deleted through the platform.

#### Scenario: Account disabled in the identity provider

- **GIVEN** a person with an interactive session, a delegated run in flight and a
  schedule
- **WHEN** their account is disabled in the identity provider
- **THEN** their standing is unchanged, their interactive access ends when their
  current token expires, and the delegated run and the scheduled occurrences stay
  authorized by their standing and permissions

#### Scenario: Account created in the identity provider

- **WHEN** a person with a newly created identity-provider account makes their
  first protected request
- **THEN** they are in good standing without any platform provisioning step, and
  their permission checks decide access

### Requirement: Control-plane startup establishes standing

With delegation enabled, the control plane SHALL, on every start and before it
serves, validate that its selected authorization model carries the standing
relations, write the default standing entry, write the standing-ready marker, and
confirm that the marker is present. Any failure in these steps SHALL stop startup.
Standing initialisation SHALL NOT require identity administration. With delegation
disabled, startup SHALL write neither the default standing entry nor the marker.

#### Scenario: Clean start with delegation enabled

- **GIVEN** a store with the standing model selected and no standing tuples, and a
  control plane granted no identity administration
- **WHEN** the control plane starts with delegation enabled
- **THEN** before it serves, the default standing entry and the ready marker exist
  and every person not suspended is in good standing

#### Scenario: Restart keeps suspensions

- **GIVEN** the default standing entry, the ready marker and a suspended person
- **WHEN** the control plane starts again
- **THEN** it rewrites the default entry and the marker without error, and the
  person remains suspended

#### Scenario: Standing cannot be established

- **WHEN** the selected model lacks the standing relations, a standing write fails,
  or the ready marker cannot be confirmed
- **THEN** the control plane refuses to start and serves no request

#### Scenario: Delegation disabled

- **WHEN** the control plane starts with delegation disabled
- **THEN** it writes no standing tuple and does not require the standing model

### Requirement: Deleting a person through the platform suspends them first

Deleting a person through the platform SHALL be the only platform operation that
ends a person's standing. After its permission and protected-account checks, the
deletion SHALL confirm that identity administration is available before changing
anything, and SHALL fail as service unavailable with nothing changed when it is
not. It SHALL write the person's suspension when the control plane's delegation is
enabled, then remove the person's other relations, admission records, background
tasks and schedules, and only after that cleanup is committed delete the
identity-provider account. The suspension SHALL survive the relation cleanup.
If the identity-provider deletion fails, a suspension already written SHALL remain
and a retried deletion SHALL complete it. If the identity-provider account is
already missing, the deletion SHALL complete the cleanup and report the person as
not found. With the control plane's delegation disabled, the deletion SHALL write
no suspension. A deletion naming the wildcard subject `*` or a userset (an id
containing `#`) SHALL report not found and change nothing, because neither names a
person. The relation cleanup of a person SHALL read only the relations naming that
person, so its cost grows with that person's relations and not with the size of
the relationship store.

#### Scenario: Deleted through the platform

- **GIVEN** the control plane's delegation is enabled and a person with relations,
  admission records, background tasks, schedules and a delegated run in flight
- **WHEN** an administrator deletes the person through the platform
- **THEN** the person is suspended before their identity-provider account is
  deleted; their other relations, admission records, tasks and schedules are
  removed while the suspension remains; and a late run-end report returns 404
  without recreating a purged record or changing the run's local terminal outcome

#### Scenario: Identity-provider deletion fails

- **GIVEN** the control plane's delegation is enabled
- **WHEN** the identity-provider step of a platform deletion fails
- **THEN** the deletion reports the failure, the person is already suspended and
  refused on their next decision, and a retried deletion completes the removal

#### Scenario: Identity-provider account already missing

- **WHEN** a person whose identity-provider account is already missing is deleted
  through the platform
- **THEN** the cleanup completes, including the suspension when the control
  plane's delegation is enabled, and the deletion reports the person as not found

#### Scenario: Identity administration unavailable

- **WHEN** a person is deleted through the platform while identity administration
  is not available to the control plane
- **THEN** the deletion fails as service unavailable and no suspension, relation,
  record, task, schedule or account is changed

#### Scenario: Control-plane delegation disabled

- **GIVEN** the control plane's delegation is disabled
- **WHEN** a person is deleted through the platform
- **THEN** no suspension is written; the person's other relations, where
  relationship authorization is enabled, and their records, tasks and schedules are
  removed; and their identity-provider account is deleted

#### Scenario: Deletion naming no person

- **GIVEN** the default standing entry and a person with relations, admission
  records and a schedule
- **WHEN** a deletion names the wildcard subject `*` or an id containing `#`,
  whether the control plane's delegation is enabled or disabled
- **THEN** the deletion reports not found, and no suspension, relation, record,
  task, schedule or account is changed

#### Scenario: Relation cleanup reads only the person's relations

- **GIVEN** a relationship store holding relations of other persons and teams, and
  a person with relations on several object types
- **WHEN** that person's relations are removed
- **THEN** every read names that person and one object type, no read enumerates
  the whole store, the person's relations other than the suspension are removed
  and every other relation remains

### Requirement: Only the standing lifecycle writes standing relations

The `active`, `suspended` and `standing_ready` relations on the platform
organization SHALL be written or deleted only by control-plane startup and person
deletion. The generic relation write and delete operations SHALL refuse them, and
removing all relations of a person SHALL leave a suspension in place. Neither an
authenticated request, personal-space self-heal nor a delegation grant SHALL write
or delete them.

#### Scenario: Generic relation operation refused

- **WHEN** a generic relation write or delete names `active`, `suspended` or
  `standing_ready` on the platform organization
- **THEN** it is refused and the store is unchanged

#### Scenario: Relation cleanup keeps the suspension

- **GIVEN** a suspended person
- **WHEN** all relations of that person are removed
- **THEN** the suspension remains

#### Scenario: Old token cannot lift a suspension

- **GIVEN** a suspended person whose access token has not expired
- **WHEN** that token is used for an authenticated request, including a
  personal-space read, or a grant names that person
- **THEN** the suspension remains, protected access is denied and subsequent
  delegated calls for that person remain denied

### Requirement: A suspension applies from the person's next decision

A suspension SHALL take effect on the person's next authorization decision at
every receiver, without any credential of the person's being involved and without
a receiver calling the control plane or the identity provider. A suspension
written before a decision SHALL be observed by it. Work already authorized SHALL
NOT be interrupted by the suspension itself. A delegated run receiving the
standing denial SHALL end with `authority_lost` and cancel its children.

#### Scenario: Delegated run after a suspension

- **GIVEN** a delegated run acting for a person and holding no credential of the
  person's
- **WHEN** the person is suspended and the run makes its next receiver call
- **THEN** the call is denied with the standing denial, the run ends with
  `authority_lost` and its children are cancelled

#### Scenario: Work already authorized

- **GIVEN** a receiver call for a person that has passed its authorization decision
- **WHEN** the person is suspended while that call executes
- **THEN** the call completes, and the suspension applies from the person's next
  authorization decision

### Requirement: Delegation enforces account standing

Enabling delegation SHALL enforce account standing on every person decision of
that service, with no separate setting. A service whose relationship engine would
not enforce — no OpenFGA, or either OIDC half disabled — SHALL refuse to build it
and SHALL not start.

#### Scenario: Delegation enabled

- **WHEN** a configuration enables delegation
- **THEN** every person decision of that service requires standing

#### Scenario: Delegation enabled where the engine would not enforce

- **WHEN** a configuration enables delegation with no OpenFGA engine or either OIDC
  half disabled
- **THEN** building the engine fails and the service does not start

### Requirement: Standing is enforced only after its model and marker are ready

The platform SHALL publish and select an authorization model containing `active`,
`suspended` and `standing_ready` for all participating readers and writers,
including deployments with pinned model IDs. A receiver enforcing standing SHALL
validate its selected model and require the standing-ready marker before it
starts, and SHALL refuse to start, reporting that account standing is not ready,
while either is missing. The marker SHALL be written only by control-plane startup,
after the default standing entry. An old pinned model, a missing marker, an
unavailable store or a non-enforcing engine SHALL NOT pass readiness, and the
marker SHALL NOT substitute for the standing check on each decision.

#### Scenario: Deployment pinned to the old model

- **GIVEN** a deployment explicitly selecting a model without the standing
  relations
- **WHEN** enforcement is attempted
- **THEN** readiness fails and standing is not enforced
- **WHEN** the new model is published, all participants select it and the control
  plane has started with delegation enabled
- **THEN** enforcement can begin and persons who are not suspended retain their
  authorized access

#### Scenario: Control plane starts before receivers

- **GIVEN** a model containing the standing relations selected by every participant
- **WHEN** the control plane starts with delegation enabled
- **THEN** it writes the default standing entry and the ready marker before it serves
- **WHEN** delegation is then enabled on a receiver
- **THEN** the receiver finds the marker and enforces standing on person decisions

#### Scenario: A receiver enabled before the marker exists

- **WHEN** a receiver starts with delegation enabled while no ready marker exists
- **THEN** it refuses to start, reporting that account standing is not ready,
  rather than refusing every person

### Requirement: No role-based access without a person

A caller holding the service role SHALL NOT obtain team read, agent execution or
tag access without a subject. Any caller-only policy SHALL be explicit and SHALL
enforce its endpoint-specific workload identity and resource/record ownership
contract. Delegation uses the foundation's trusted client/subject binding and the
person's permissions. The foundation's explicit own-credential runtime guards
remain exceptions in this step.

#### Scenario: Service bearer without a grant on a former shortcut

- **GIVEN** a bearer holding the service role and no grant
- **WHEN** it requests team read, agent execution, tag, table, ingestion,
  library-sync or knowledge-base access
- **THEN** the request is denied

### Requirement: An allow-listed caller's grant admits a run

The runtime SHALL accept the grant parameters from an allow-listed caller as
admission input, accept them as a receiver does, write the run record from them,
check the person's standing and agent permission, register the run under the
foundation's workload-report contract, and make downstream calls for that person.
It SHALL use its own workload bearer for registration and downstream calls, without
requiring a person token or an active session. Every boundary SHALL retain its
authenticated caller and the person/run in request context and required product
records. Delegation logs SHALL exclude identifiers under the foundation policy.

#### Scenario: Evaluation run for a campaign creator

- **GIVEN** the evaluation worker presents its bearer and the grant parameters
  naming an authorized campaign creator whose session has ended
- **WHEN** the run is admitted and calls a receiver
- **THEN** admission records retain the worker as caller, registry and downstream
  context identify the runtime as their authenticated caller, and all carry the
  campaign creator and same run without a receiver consulting the registry or
  emitting any identifiers in logs

### Requirement: Personal-team admission requires current standing

New run registrations, background starts, schedule creation and occurrences SHALL
check the person's current standing explicitly even when team access resolves
through a personal-team shortcut. The fresh standing check and private admission
write SHALL share the cross-replica critical section used by account deletion.

#### Scenario: Revoked person has personal-team access

- **GIVEN** a person's token remains valid and their personal-team access shortcut succeeds
- **WHEN** they lack active standing and request a run, background task or schedule
- **THEN** no admission or private payload is persisted and no execution is dispatched

#### Scenario: Deletion overtakes an in-flight admission

- **GIVEN** an admission checked permissions before waiting for the lifecycle lock
- **WHEN** deletion removes standing and purges records before that lock is acquired
- **THEN** the admission's fresh check fails and the removed records remain absent
