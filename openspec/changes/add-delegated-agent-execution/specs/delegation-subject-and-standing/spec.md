## Purpose

Defines the separation of the calling workload from the person a request acts
for, the standing requirement applied to every authorization decision, and the
rule that keeps role-based access naming no person away from delegation callers.
Run-stop requirements cover ReAct and DeepAgent execution.

## ADDED Requirements

### Requirement: A request has a caller and a subject

Every authenticated request SHALL carry a caller (the identity authenticated by
the bearer) and, when present, a subject (the authenticated or asserted person). Authorization
decisions SHALL use the subject. A service-role check SHALL evaluate the caller
only. An asserted person SHALL NOT satisfy the service-role predicate, and a true
caller predicate SHALL NOT grant the subject access to a delegated operation.

#### Scenario: Asserted person never satisfies a service-role check

- **GIVEN** a service caller holding the service role and a subject built from a
  grant
- **WHEN** their identities and permission for a delegated operation are evaluated
- **THEN** the caller satisfies the service-role predicate, the asserted subject
  does not, and access still requires the subject's standing and permission

### Requirement: Standing is required on every decision

When account standing is enforced, the authorization engine SHALL require a person's
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
- **AND** a delegated REST or tool client preserves that cause as `authority_lost`,
  ending execution and awaiting descendant cancellation without ordinary retry

#### Scenario: An unrelated service is unavailable

- **WHEN** a delegated call receives HTTP 503 without a standing-unavailable refusal
- **THEN** the status alone does not establish lost authority and ordinary error
  handling remains applicable

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
Delegated runs acting for that person SHALL keep their authorization, subject to
the person's standing and permissions, until the person is deleted through the
platform.

#### Scenario: Account disabled in the identity provider

- **GIVEN** a person with an interactive session and a delegated run in flight
- **WHEN** their account is disabled in the identity provider
- **THEN** their standing is unchanged, their interactive access ends when their
  current token expires, and the delegated run stays authorized by their standing
  and permissions

#### Scenario: Account created in the identity provider

- **WHEN** a person with a newly created identity-provider account makes their
  first protected request
- **THEN** they are in good standing without any platform provisioning step, and
  their permission checks decide access

### Requirement: Control-plane startup establishes standing

With either delegation switch on, the control plane SHALL, on every start and
before it serves, validate that its selected authorization model carries the standing
relations, write the default standing entry, write the standing-ready marker, and
confirm that the marker is present. Any failure in these steps SHALL stop startup.
Standing initialisation SHALL NOT require identity administration. With both
delegation switches off, startup SHALL write neither the default standing entry
nor the marker.

#### Scenario: Clean start with a delegation switch on

- **GIVEN** a store with the standing model selected and no standing tuples, and a
  control plane granted no identity administration
- **WHEN** the control plane starts with a delegation switch on
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

#### Scenario: Both delegation switches off

- **WHEN** the control plane starts with both delegation switches off
- **THEN** it writes no standing tuple and does not require the standing model

### Requirement: Deleting a person through the platform suspends them first

Deleting a person through the platform SHALL be the only platform operation that
ends a person's standing. After its permission and protected-account checks, a
deletion naming the wildcard subject `*` or a userset (an id containing `#`) SHALL
report not found and change nothing, because neither names a person. The deletion
SHALL then confirm that identity administration is available before changing
anything, and SHALL fail as service unavailable with nothing changed when it is
not. It SHALL write the person's suspension when the control plane enforces
account standing, and only then delete the identity-provider account. It SHALL
leave the person's other relations in place. If the identity-provider deletion
fails, a suspension already written SHALL remain and a retried deletion SHALL
complete it. If the identity-provider account is already missing, the deletion
SHALL report the person as not found after writing the suspension. Without
standing enforcement the deletion SHALL write no suspension.

#### Scenario: Deleted through the platform

- **GIVEN** the control plane enforces account standing and a person with
  relations and a delegated run in flight
- **WHEN** an administrator deletes the person through the platform
- **THEN** the person is suspended before their identity-provider account is
  deleted, their other relations remain, and the run ends with `authority_lost`
  at its next receiver call

#### Scenario: Identity-provider deletion fails

- **GIVEN** the control plane enforces account standing
- **WHEN** the identity-provider step of a platform deletion fails
- **THEN** the deletion reports the failure, the person is already suspended and
  refused on their next decision, and a retried deletion completes the removal

#### Scenario: Identity-provider account already missing

- **WHEN** a person whose identity-provider account is already missing is deleted
  through the platform
- **THEN** the suspension is written when the control plane enforces account
  standing, and the deletion reports the person as not found

#### Scenario: Identity administration unavailable

- **WHEN** a person is deleted through the platform while identity administration
  is not available to the control plane
- **THEN** the deletion fails as service unavailable and no suspension, relation or
  account is changed

#### Scenario: Standing not enforced

- **GIVEN** the control plane does not enforce account standing
- **WHEN** a person is deleted through the platform
- **THEN** no suspension is written, the person's relations remain and their
  identity-provider account is deleted

#### Scenario: Deletion naming no person

- **GIVEN** the default standing entry and a person with relations
- **WHEN** a deletion names the wildcard subject `*` or an id containing `#`,
  whether or not the control plane enforces account standing
- **THEN** the deletion reports not found, and no suspension, relation or account
  is changed

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

Turning either delegation switch on SHALL enforce account standing on every person decision of
that service, with no separate setting. A service whose relationship engine would
not enforce — no OpenFGA, or either OIDC half disabled — SHALL refuse to build it
and SHALL not start.

#### Scenario: A delegation switch on

- **WHEN** a configuration turns either delegation switch on
- **THEN** every person decision of that service requires standing

#### Scenario: A delegation switch on where the engine would not enforce

- **WHEN** a configuration turns a delegation switch on with no OpenFGA engine or either OIDC
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
  plane has started with a delegation switch on
- **THEN** enforcement can begin and persons who are not suspended retain their
  authorized access

#### Scenario: Control plane starts before receivers

- **GIVEN** a model containing the standing relations selected by every participant
- **WHEN** the control plane starts with a delegation switch on
- **THEN** it writes the default standing entry and the ready marker before it serves
- **WHEN** a delegation switch is then turned on at a receiver
- **THEN** the receiver finds the marker and enforces standing on person decisions

#### Scenario: A receiver switched on before the marker exists

- **WHEN** a receiver starts with a delegation switch on while no ready marker exists
- **THEN** it refuses to start, reporting that account standing is not ready,
  rather than refusing every person

### Requirement: Service-identity shortcuts are closed to delegation callers

A shortcut that gives a caller holding the service role access without a subject —
team read, tag, table and ingestion access, the model override, and managed agent
execution with its per-tool recheck — SHALL apply only when that caller does not
hold the delegation caller role. The caller role SHALL be read from the verified
token whatever the delegation switches. A caller holding it SHALL NOT obtain
team read, agent execution, tag, table or ingestion access through a service-role
shortcut. Its own-identity access SHALL follow ordinary endpoint authorization. A
caller without it SHALL keep the shortcuts and run as itself on its own bearer.
Any caller-only policy SHALL be explicit and SHALL enforce its endpoint-specific
workload identity and resource/record ownership contract. Delegation trusts the
caller role and applies the person's permissions; the explicit own-credential
runtime guards remain exceptions. A knowledge-base pod's own-workload operations are such caller-only
policies: reading its run's configuration, bound to the exact client of its
definition, and mirroring into the library its instance granted it. A run names
no person, so these SHALL NOT require a grant, and a person named by a grant SHALL
NOT read a run's configuration.

#### Scenario: A service identity without the caller role keeps its shortcuts

- **GIVEN** a bearer holding the service role and not the delegation caller role,
  with no grant, whatever the delegation switches
- **WHEN** it requests team read, tag, table or ingestion access, or managed agent
  execution in a team
- **THEN** the shortcut applies as it does with delegation off, and a run it
  starts while `act_for_people` is on has no run record and presents its own
  bearer on every outbound call

#### Scenario: A delegation client acting as itself takes no shortcut

- **GIVEN** a bearer holding both the service role and the delegation caller role,
  with no grant, whatever the delegation switches
- **WHEN** it requests team read, tag, table or ingestion access, the model
  override or managed agent execution
- **THEN** no service-identity shortcut applies: the request is decided on the
  relations of the bearer's own identity, and agent execution is refused as needing
  a person where the runtime acts for people

#### Scenario: A knowledge-base pod runs without a person

- **GIVEN** a receiver that accepts delegated calls and a pod bearer holding the
  service role, issued to the client its definition is bound to, with no grant
- **WHEN** it reads its run's configuration and writes into its instance's library
- **THEN** both succeed, while a bearer of another client, a bearer holding only
  the delegation caller role, and a person named by a grant are refused the run's
  configuration

#### Scenario: Caller-role holder without a grant asks to execute

- **GIVEN** `act_for_people` on and a bearer carrying the delegation caller role
  but no grant
- **WHEN** it requests agent execution
- **THEN** execution is refused as needing a person

### Requirement: A role-holding caller's grant admits a run

The runtime SHALL accept the grant parameters from a role-holding caller as
admission input, accept them as a receiver does, write the pod-local run record
from them, check the person's standing and agent permission, and make downstream
calls for that person. It SHALL use its own workload bearer for downstream calls,
without requiring a person token or an active session, and no control-plane call
SHALL record the run. Every boundary SHALL retain its authenticated caller and the
person/run in request context and required product records. Delegation logs
SHALL exclude identifiers.

#### Scenario: Run admitted for a person whose session has ended

- **GIVEN** a role-holding workload presents its bearer and the grant parameters
  naming an authorized person whose session has ended
- **WHEN** the run is admitted and calls a receiver
- **THEN** the run record names that person and run and carries no roles, the
  downstream call presents the runtime's workload bearer and the same grant, and
  no log names the person, the caller, the run or the bearer

### Requirement: Runtime admission requires current standing

Admission of a delegated run SHALL require the person's current standing before
execution: a direct target SHALL check it explicitly, and a managed target through
its standing-gated team check, the person's personal team included.

#### Scenario: A suspended person asks for a run

- **GIVEN** `act_for_people` on and a person who holds a suspension and whose
  token is still valid
- **WHEN** they request a run, in a team or in their personal team
- **THEN** admission is refused and no execution starts

### Requirement: The user whitelist applies to the subject

Where a deployment enables the user whitelist, an asserted person SHALL be
checked against it as an authenticated person is. The whitelist SHALL accept
`uid:<subject>` entries beside email entries. An authenticated person SHALL be
admitted by a matching subject or email entry, an asserted person by a matching
subject entry only. The check SHALL need no identity-provider or control-plane
lookup.

#### Scenario: Asserted person outside the whitelist

- **GIVEN** a whitelist listing a person by email only
- **WHEN** a trusted workload asserts that person through a grant
- **THEN** the request is refused until the whitelist lists the person's subject
  identifier
