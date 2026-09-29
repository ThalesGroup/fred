## Purpose

Defines the separation of the calling workload from the person a request acts
for, the account status check made once per authenticated request, and the
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
  does not, and access still requires the subject's active account and permission

### Requirement: Account status is decided once per request

When account status is enforced, a service SHALL check once per authenticated
request, where the request's subject is established and before the route runs,
that the subject does not hold `organization#suspended`. The subject SHALL be the
signed-in person, the person named by a verified grant or the authenticated
service identity, with no exemption. The check SHALL run at higher consistency
and SHALL produce a distinct authorization denial when the subject is suspended
or the check cannot run, before any handler, lookup or permission check of the
request. Checks, batch checks and list lookups SHALL NOT repeat that check and
SHALL keep the consistency their caller asks for. A service with a delegation
switch on and no relationship engine installed for the check SHALL refuse every
authenticated request as unavailable. A delegated run receiving the account status
denial SHALL end with `authority_lost` and cancel its children.

#### Scenario: Direct grant for a suspended person

- **GIVEN** a suspended person who owns a tag directly
- **WHEN** their run reads the tag
- **THEN** the read is denied

#### Scenario: List lookup for a suspended person

- **GIVEN** a delegated run acting for a suspended person
- **WHEN** its next call asks a receiver to list resources for them
- **THEN** the receiver refuses the request with the account status denial before any
  lookup runs, the run ends with `authority_lost`, and its children are
  cancelled

#### Scenario: One account status check per request

- **GIVEN** account status enforcement and an active subject
- **WHEN** a request makes several checks, batch checks and list lookups
- **THEN** exactly one account status check is made for the request, before the first
  of them, and the checks and lookups use the consistency their caller asked for

#### Scenario: Every kind of subject is checked

- **GIVEN** account status enforcement
- **WHEN** a signed-in person, a person named by a grant or a service identity
  makes an authenticated request
- **THEN** that subject's account status is checked once before the route runs

#### Scenario: Personal space without a relationship check

- **GIVEN** a suspended person
- **WHEN** a runtime-binding lookup or an execution preparation targets their
  personal team, whether a grant names them or they present their own bearer
- **THEN** the request is refused with HTTP 403 and cause `account_suspended`, or
  with HTTP 503 and cause `account_status_unavailable` when account status cannot be
  established, and nothing is resolved

#### Scenario: Account status check without a relationship engine

- **GIVEN** a service with a delegation switch on and no relationship engine
  installed for the account status check
- **WHEN** an authenticated request arrives
- **THEN** it is refused with HTTP 503 and cause `account_status_unavailable`

#### Scenario: Active person with no matching accessible resources

- **GIVEN** an active person with no accessible resources matching a listing
- **WHEN** resources are listed for them
- **THEN** an ordinary successful empty list is permitted without ending the run

#### Scenario: Account status check unavailable

- **WHEN** the account status check cannot be evaluated
- **THEN** the receiver returns the bounded `account_status_unavailable` failure (HTTP
  503), without upstream details, and no data is returned
- **AND** no authenticated endpoint is exempt, including profile and bootstrap
  requests
- **AND** a delegated REST or tool client preserves that cause as `authority_lost`,
  ending execution and awaiting descendant cancellation without ordinary retry

#### Scenario: An unrelated service is unavailable

- **WHEN** a delegated call receives HTTP 503 without an `account_status_unavailable` refusal
- **THEN** the status alone does not establish lost authority and ordinary error
  handling remains applicable

### Requirement: Account status is a block list owned by the platform

Every authenticated person SHALL be active unless the platform has
suspended them. Account status SHALL be decided from `organization#suspended` alone: a
person who holds it is not active, and no stored entry SHALL be required
for any other person to be active. The platform SHALL be the only source
of account status: no identity-provider listing, account state or administration right
SHALL be read to decide or change it. A service identity that is a request's
subject SHALL be decided by the same rule, and its access SHALL still require its
own relations.

#### Scenario: Person never suspended

- **GIVEN** a person who holds no suspension
- **WHEN** a request names that person as its subject
- **THEN** the account is active without any per-person or platform-wide entry, and the
  request's decisions depend on the person's permission on the object

#### Scenario: Suspended person

- **GIVEN** a person who holds `organization#suspended`
- **WHEN** a request names them as its subject
- **THEN** the account is not active and the typed account status denial is returned
  before any check or lookup, whatever other relations the person holds

#### Scenario: Service identity checked as a person

- **GIVEN** a service identity that holds no suspension, such as a knowledge-base
  pod account, authenticating a request
- **WHEN** its account status is checked
- **THEN** its account is active, and access still requires its own relations on
  the object

#### Scenario: Store without suspension tuples

- **GIVEN** a store that holds no suspension
- **WHEN** any subject makes a request
- **THEN** the subject's account is active and its permissions decide access

### Requirement: Identity-provider account changes do not change account status

Creating, disabling, re-enabling or deleting an account in the identity provider
SHALL NOT change the person's account status. When the account is disabled or deleted
there, the person's interactive access SHALL end when their current token expires.
Delegated runs acting for that person SHALL keep their authorization, subject to
the person's account status and permissions, until the person is deleted through the
platform.

#### Scenario: Account disabled in the identity provider

- **GIVEN** a person with an interactive session and a delegated run in flight
- **WHEN** their account is disabled in the identity provider
- **THEN** their account status is unchanged, their interactive access ends when
  their current token expires, and the delegated run stays authorized by their
  account status and permissions

#### Scenario: Account created in the identity provider

- **WHEN** a person with a newly created identity-provider account makes their
  first protected request
- **THEN** their account is active without any platform provisioning step, and
  their permission checks decide access

### Requirement: Control-plane startup validates the account status model

With either delegation switch on, the control plane SHALL, on every start and
before it serves, validate that its selected authorization model carries the
`suspended` relation, and a failed validation SHALL stop startup. Startup SHALL
write no suspension tuple and SHALL NOT require identity administration.

#### Scenario: Clean start with a delegation switch on

- **GIVEN** a store with the account status model selected and no suspension tuples, and a
  control plane granted no identity administration
- **WHEN** the control plane starts with a delegation switch on
- **THEN** it serves without writing any suspension tuple, and every person not
  suspended has an active account

#### Scenario: Restart keeps suspensions

- **GIVEN** a suspended person
- **WHEN** the control plane starts again
- **THEN** the person remains suspended

#### Scenario: Incompatible model

- **WHEN** the selected model lacks the `suspended` relation or the store cannot
  be read
- **THEN** the control plane refuses to start and serves no request

#### Scenario: Both delegation switches off

- **WHEN** the control plane starts with both delegation switches off
- **THEN** it writes no suspension tuple and does not require the account status model

### Requirement: Deleting a person through the platform suspends them first

Deleting a person through the platform SHALL be the only platform operation that
suspends a person's account. After its permission and protected-account checks, a
deletion naming the wildcard subject `*` or a userset (an id containing `#`) SHALL
report not found and change nothing, because neither names a person. The deletion
SHALL then confirm that identity administration is available before changing
anything, and SHALL fail as service unavailable with nothing changed when it is
not. It SHALL write the person's suspension when the control plane enforces
account status, and only then delete the identity-provider account. It SHALL
leave the person's other relations in place. If the identity-provider deletion
fails, a suspension already written SHALL remain and a retried deletion SHALL
complete it. If the identity-provider account is already missing, the deletion
SHALL report the person as not found after writing the suspension. Without
account status enforcement the deletion SHALL write no suspension.

#### Scenario: Deleted through the platform

- **GIVEN** the control plane enforces account status and a person with
  relations and a delegated run in flight
- **WHEN** an administrator deletes the person through the platform
- **THEN** the person is suspended before their identity-provider account is
  deleted, their other relations remain, and the run ends with `authority_lost`
  at its next receiver call

#### Scenario: Identity-provider deletion fails

- **GIVEN** the control plane enforces account status
- **WHEN** the identity-provider step of a platform deletion fails
- **THEN** the deletion reports the failure, the person is already suspended and
  refused on their next request, and a retried deletion completes the removal

#### Scenario: Identity-provider account already missing

- **WHEN** a person whose identity-provider account is already missing is deleted
  through the platform
- **THEN** the suspension is written when the control plane enforces account
  status, and the deletion reports the person as not found

#### Scenario: Identity administration unavailable

- **WHEN** a person is deleted through the platform while identity administration
  is not available to the control plane
- **THEN** the deletion fails as service unavailable and no suspension, relation or
  account is changed

#### Scenario: Account status not enforced

- **GIVEN** the control plane does not enforce account status
- **WHEN** a person is deleted through the platform
- **THEN** no suspension is written, the person's relations remain and their
  identity-provider account is deleted

#### Scenario: Deletion naming no person

- **GIVEN** a person with relations
- **WHEN** a deletion names the wildcard subject `*` or an id containing `#`,
  whether or not the control plane enforces account status
- **THEN** the deletion reports not found, and no suspension, relation or account
  is changed

### Requirement: Only the account lifecycle writes account status relations

The `suspended` relation on the platform organization SHALL be written only by
person deletion and deleted by no platform operation. The generic relation write
and delete operations SHALL refuse it, and removing all relations of a person
SHALL leave a suspension in place. Neither an authenticated request,
personal-space self-heal nor a delegation grant SHALL write or delete it.

#### Scenario: Generic relation operation refused

- **WHEN** a generic relation write or delete names `suspended` on the platform
  organization
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

### Requirement: A suspension applies from the person's next request

A suspension SHALL take effect on the next request naming the person as its
subject at every receiver, and on the next tool call of a delegated run acting for them,
without any credential of the person's being involved and without a receiver
calling the control plane or the identity provider. A suspension written before a
request's account status check SHALL be observed by it. Work already authorized SHALL
NOT be interrupted by the suspension itself: a request that has passed its
account status check SHALL complete, and background work admitted by a request before
the suspension SHALL finish without an account status check of its own. A delegated run
receiving the account status denial SHALL end with `authority_lost` and cancel its
children.

#### Scenario: Delegated run after a suspension

- **GIVEN** a delegated run acting for a person and holding no credential of the
  person's
- **WHEN** the person is suspended and the run makes its next receiver call
- **THEN** the call is denied with the account status denial, the run ends with
  `authority_lost` and its children are cancelled

#### Scenario: Work already authorized

- **GIVEN** a receiver call for a person that has passed its account status check
- **WHEN** the person is suspended while that call executes
- **THEN** the call completes, and the suspension applies from the person's next
  request

#### Scenario: Background work already admitted

- **GIVEN** background processing admitted by a person's request, such as
  document ingestion
- **WHEN** the person is suspended before or while it runs
- **THEN** the processing finishes without an account status check of its own, and the
  person's next request is refused with the account status denial

### Requirement: Delegation enforces account status

Turning either delegation switch on SHALL enforce account status on every
authenticated request that service serves, service identities included, with no
separate setting; a tool mount's initialization and tool listing only
authenticate, and each mounted tool call is checked by the route serving it. A service whose relationship engine would
not enforce — no OpenFGA, or either OIDC half disabled — SHALL refuse to build it
and SHALL not start.

#### Scenario: A delegation switch on

- **WHEN** a configuration turns either delegation switch on
- **THEN** every authenticated request to that service, other than a tool
  mount's initialization and tool listing, requires its subject's account to be
  active

#### Scenario: A delegation switch on where the engine would not enforce

- **WHEN** a configuration turns a delegation switch on with no OpenFGA engine or either OIDC
  half disabled
- **THEN** building the engine fails and the service does not start

### Requirement: Account status is enforced only with a compatible model

The platform SHALL publish and select an authorization model containing
`suspended` for all participating readers and writers, including deployments with
pinned model IDs. A service enforcing account status SHALL validate its selected model
before it starts and SHALL refuse to start while the model lacks `suspended`. An
old pinned model, an unavailable store or a non-enforcing engine SHALL NOT pass
the startup check. Services SHALL NOT depend on one another's startup order.

#### Scenario: Deployment pinned to the old model

- **GIVEN** a deployment explicitly selecting a model without the `suspended`
  relation
- **WHEN** enforcement is attempted
- **THEN** the startup check fails and account status is not enforced
- **WHEN** the new model is published and all participants select it
- **THEN** enforcement can begin and persons who are not suspended retain their
  authorized access

#### Scenario: Services start in any order

- **GIVEN** a model containing `suspended` selected by every participant
- **WHEN** a receiver starts with a delegation switch on before the control plane
- **THEN** it starts and enforces account status on every authenticated request

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
from them, check the person's account status and agent permission, and make downstream
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

### Requirement: Runtime admission requires an active account

Admission of a delegated run SHALL require the person's account to be active
before execution, through the request's account status check, which runs before
admission for direct and managed targets, the person's personal team included.
Admission's team checks SHALL NOT repeat it.

#### Scenario: A suspended person asks for a run

- **GIVEN** `act_for_people` on and a person who holds a suspension and whose
  token is still valid
- **WHEN** they request a run, in a team or in their personal team
- **THEN** the request is refused with the account status denial before any team check,
  and no execution starts

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
