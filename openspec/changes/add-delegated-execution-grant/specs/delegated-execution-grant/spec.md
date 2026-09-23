## Purpose

Defines how an agent run identifies the person it acts for after local admission,
how receiving services authenticate and authorize the calling workload's statement,
and how a run behaves when its authority ends or its time budget is exhausted.

## ADDED Requirements

### Requirement: The person's credential is never retained for execution

Under delegation the platform SHALL use the person's access token only for local
admission or authenticated owner reattachment to a supported stream. Reattachment
SHALL NOT supply credentials to the running execution or create a new admission.
The platform SHALL NOT retain the person's token beyond authenticating those
requests, store it in run state, forward, exchange or renew it. No outbound call
made for the run SHALL carry it.

#### Scenario: The person's token expires during the run

- **GIVEN** a run admitted with a valid token and delegation enabled
- **WHEN** that token expires while the run is still working
- **THEN** downstream calls made for the run continue to succeed

#### Scenario: Outbound requests never carry the person's bearer

- **GIVEN** delegation enabled
- **WHEN** any downstream call is made for the run
- **THEN** its authorization header carries the platform's workload token and not
  the person's token

#### Scenario: Owner reauthentication does not replace execution credentials

- **GIVEN** a supported reconnect to an admitted run
- **WHEN** its owner presents a current token to reattach
- **THEN** the runtime authenticates that request locally and discards the token;
  the existing run keeps its workload credential provider and admission record

### Requirement: Every delegated call authenticates its caller and identifies its subject

A delegated call SHALL carry the platform's workload credential and a delegation
grant made of the request parameters `person`, `run` and `agent`. A receiver
SHALL treat a call missing either as acting for nobody.

#### Scenario: Grant without an allow-listed bearer

- **GIVEN** grant parameters
- **WHEN** they arrive without a valid workload bearer from an allow-listed client
- **THEN** the parameters are ignored, the request has no subject, and the attempt
  is audited

#### Scenario: Bearer without a grant

- **GIVEN** a valid workload bearer from an allow-listed client
- **WHEN** no grant parameters accompany it
- **THEN** the request is treated as a service caller acting for nobody

### Requirement: A grant is accepted only as an allow-listed caller's statement

A receiver SHALL accept the grant parameters as the caller's statement only when
the accompanying access token is valid, its verified client and service-account
subject match the receiver's configured workload identity. An `azp` claim alone SHALL NOT
establish that identity. The person SHALL be an immutable subject identifier in
the configured issuer's realm, not an email or username. The grant SHALL have no
lifetime of its own, SHALL be presented on every call including retries, and a
receiver SHALL NOT forward it to another service.

#### Scenario: Statement from a client not on the allow-list

- **WHEN** grant parameters arrive with a valid bearer whose client is not
  allow-listed
- **THEN** the request has no subject

#### Scenario: User token shares an allowed client claim

- **GIVEN** a valid user token with an allowed client claim or service role but
  without the configured service-account subject
- **WHEN** it carries delegation parameters
- **THEN** it cannot establish a delegated subject or invoke delegated operations

#### Scenario: Malformed grant

- **WHEN** the parameters are incomplete or malformed
- **THEN** the request has no subject

#### Scenario: A call outlives the bearer

- **GIVEN** a call accepted with a valid bearer and grant
- **WHEN** the bearer expires while the receiver is still processing the call
- **THEN** the call completes and its result is returned

### Requirement: Receivers trust workloads and apply the person's permissions

Each receiver SHALL require an explicitly trusted workload client/service-account
pair and SHALL apply the asserted person's function, object, field and team
permissions. Administrative actions SHALL retain their normal
user authorization. Existing explicit own-credential guards SHALL remain in force.
Receivers SHALL make these checks locally without consulting the control plane
for a credential or delegation decision.

Caller-policy configuration SHALL contain client and service-account identity
bindings. Unknown configuration fields SHALL be rejected.

#### Scenario: Trusted workload acts for an authorized person

- **GIVEN** a valid trusted workload, a valid grant and an authorized person
- **WHEN** it invokes a delegation-capable endpoint
- **THEN** delegation succeeds and the endpoint applies the person's permissions

#### Scenario: Delegated action targets unauthorized data

- **GIVEN** a trusted workload acting for a person
- **WHEN** it targets an action, object, field or team outside the person's permissions
- **THEN** access is denied without a partial write or protected data disclosure

#### Scenario: Workload role cannot authorize an administrative action for a person

- **GIVEN** a trusted workload whose service account has privileged roles
- **WHEN** its asserted person lacks the endpoint's administrative permission
- **THEN** access is denied based on the person's authorization

### Requirement: Only the run record names the person

The `person`, `run` and `agent` parameters SHALL come from the record written at
admission. After admission, no execution request argument, tool input or model
output SHALL override them, and a run without a record SHALL make no delegated call.

#### Scenario: Call without a record

- **WHEN** a delegated call is attempted for a run id that has no admission record
- **THEN** no call is made

#### Scenario: Tool input cannot name a subject

- **GIVEN** a tool call whose arguments contain a user identifier
- **WHEN** the runtime makes the downstream call
- **THEN** the grant names the admitted person, not the identifier in the arguments

### Requirement: An asserted person is distinct from an authenticated one

A principal built from a grant SHALL be a distinct kind, SHALL never carry the
service role, and SHALL be rejected by any endpoint with an explicit guard
requiring the directly authenticated caller. The runtime endpoint inventory in
[the design](../../design.md#retained-own-credential-endpoint-restrictions) SHALL
retain these guards; this step SHALL NOT claim complete user/agent parity.

#### Scenario: Service-role shortcuts do not apply

- **GIVEN** a principal built from a grant
- **WHEN** a service-role check is evaluated on it
- **THEN** the check is false

#### Scenario: Retained runtime guard rejects a delegated person

- **GIVEN** a trusted workload and valid user grant
- **WHEN** it calls a runtime endpoint listed as requiring the caller's own credential
- **THEN** the request remains rejected before protected work, including the
  reconnect branch and the OpenAI-compatible chat endpoint

### Requirement: Permission checks are live on the asserted person

A receiver SHALL evaluate the same permission checks for an asserted person as
for an authenticated one, against current relations, on every call.

#### Scenario: Permission removed mid-run

- **GIVEN** a run acting for a person
- **WHEN** the person's team permission is removed
- **THEN** the next call for that run is denied

### Requirement: Authority loss is typed and terminal

When a receiver denies a call for lost authority, the run SHALL end with the
terminal error event carrying reason `authority_lost`, its children SHALL be
cancelled, the message SHALL be a bounded platform-owned sentence with no upstream
detail, and the call SHALL NOT be retried under the platform's own identity.

#### Scenario: Denied mid-run

- **WHEN** a downstream call returns an authorization failure
- **THEN** the run ends with reason `authority_lost`, all children are cancelled,
  and no further execution, tool or data call is made for the run; only the
  narrowly authorized terminal lifecycle report is permitted afterward

#### Scenario: Upstream detail is not exposed

- **GIVEN** an upstream error body containing a marker string
- **WHEN** the run ends for lost authority
- **THEN** the marker appears in no event, transcript, log, trace or checkpoint

### Requirement: Every run has a ceiling

A run SHALL end with reason `run_ceiling_reached` when its wall-clock budget is
exhausted, and SHALL NOT spawn more concurrent children than the configured bound.
The wall-clock budget SHALL use the deployment default unless the agent has a
configured override. Invalid limits SHALL be rejected before admission.
Per-call timeouts SHALL be unaffected.

Nested child work that cannot immediately acquire capacity held by its ancestors
SHALL end the run with `child_limit_reached` without exceeding the child bound or
waiting for the wall-clock ceiling. Ordinary sibling work MAY queue for capacity.

#### Scenario: Ceiling reached

- **GIVEN** a run whose budget is exhausted
- **WHEN** the budget elapses
- **THEN** the run ends with reason `run_ceiling_reached` and its children are
  cancelled

#### Scenario: Agent setting overrides the deployment ceiling

- **GIVEN** two agents, only one with a configured wall-clock override
- **WHEN** each starts a run
- **THEN** one run uses that override and the other uses the deployment default,
  while their per-call timeouts are unchanged

#### Scenario: Nested child exhausts capacity

- **GIVEN** the configured child capacity is occupied and a running child requests
  a descendant
- **WHEN** that descendant cannot acquire capacity immediately
- **THEN** no additional child is spawned, the run ends with
  `child_limit_reached`, and its existing children are cancelled

### Requirement: Every run is registered

The control plane SHALL record a run at admission — person, team, agent, reporting
program, start time and ceiling — from a report authenticated with an allow-listed
workload's token that it verifies itself. It SHALL authorize its own API for the
asserted person, derive the reporting program from that bearer, and SHALL NOT
require or receive the person's token. This SHALL apply both to admission with
the person's credential and to supported trusted-workload admission. Registration
failure SHALL prevent execution. The control plane SHALL record how the run ended
and SHALL NOT be consulted by any receiver to validate a delegated call. Run-end
reporting SHALL be an explicit caller-only operation restricted to the authenticated
reporting program for that existing run; it SHALL allow only a terminal outcome
update and SHALL remain available when the person loses standing. If account
deletion has purged the record, run-end SHALL return 404 without recreating it;
the runtime SHALL preserve its local terminal outcome and SHALL NOT retry that
report. End-record retention SHALL NOT override account-deletion purging.

#### Scenario: Run recorded at admission

- **WHEN** a run is admitted under delegation
- **THEN** the control plane holds a record naming the person, team, agent and
  reporting program, received using the workload's token only

#### Scenario: Registration without a trusted workload token

- **WHEN** a caller asks to record a run without a valid allow-listed workload
  token, or the asserted person fails the endpoint's permission check
- **THEN** no record is written

#### Scenario: Registration after the person's session ends

- **GIVEN** a supported trusted-workload admission for an authorized person with
  no active identity-provider session
- **WHEN** the runtime registers it using its own workload bearer and the record
- **THEN** registration succeeds without a person token, the record names the
  runtime as reporting program, and receivers make no registry lookup

#### Scenario: End recorded

- **GIVEN** a registered run whose lifecycle record has not been purged
- **WHEN** a run ends
- **THEN** its record carries the reason it ended

#### Scenario: Lost authority does not prevent reporting the end

- **GIVEN** a registered run whose person loses standing
- **WHEN** its authenticated reporting program reports `authority_lost`
- **THEN** that terminal outcome is recorded without changing the run's person or
  granting further execution, and a different program cannot update the record

#### Scenario: End report after account deletion

- **GIVEN** account deletion has removed standing and purged a running job's record
- **WHEN** that job stops for lost authority and its workload reports the end
- **THEN** run-end returns 404, no record is recreated, no report is retried and
  the job remains terminal with its children cancelled

### Requirement: MCP servers authenticate by declared mode

Under delegation the runtime SHALL send the workload bearer and the grant, outside
tool arguments, to a server in `delegated` mode, SHALL refuse to activate a server
in `user_token` mode with reason `delegation_unavailable`, and SHALL send no
credential to a server in `no_token` mode.

#### Scenario: User-token server under delegation

- **GIVEN** delegation enabled and a server declared `user_token`
- **WHEN** the run activates its tools
- **THEN** activation fails with reason `delegation_unavailable` and no bearer is sent

### Requirement: The workload token is accepted by every receiver

A workload token issued to the agent backend or to an installed application
SHALL authenticate without modification at its intended receiving services when
signature, allowed algorithm, trusted issuer/key source, validity, access-token
purpose and audience checks pass. The receiver SHALL bind its verified client
claim to the configured service-account subject. Successful authentication SHALL
NOT bypass the trusted client/subject binding or the person's authorization.
Shared deployments SHALL enforce strict issuer and audience validation.

#### Scenario: Accepted under strict audience validation

- **GIVEN** a receiver validating audiences
- **WHEN** a call arrives with the agent backend's workload token
- **THEN** the token is accepted and the caller is identified as the agent
  backend's client

#### Scenario: Invalid token context

- **WHEN** a request presents a token with a wrong issuer, audience, purpose,
  signature, algorithm, key source or validity period
- **THEN** the receiver rejects it before trusting delegation parameters

### Requirement: Deployment protects delegated transport and credentials

Delegated traffic and its token, key-discovery and authorization dependencies
SHALL use authenticated encrypted transport without plaintext fallback. Workload
secrets SHALL be stored in the deployment's managed secret facility with restricted
access. Workload clients SHALL enable only required service-account flows and
SHALL be separate from user-facing clients. These controls SHALL use existing
identity-provider, transport and secret-management mechanisms, without custom
grant cryptography in Fred.

#### Scenario: Untrusted transport peer

- **WHEN** a delegated dependency presents an untrusted certificate or a connection
  would fall back to plaintext
- **THEN** the connection fails without sending credentials or delegation data

#### Scenario: Workload client requested through a user flow

- **WHEN** a user authorization or password flow is requested for a delegation workload client
- **THEN** the identity provider refuses it and issues no delegation-capable token

### Requirement: Delegation requires user authentication

The delegation flag SHALL be honoured only when user authentication is enabled.
With authentication disabled the platform SHALL refuse to start with the flag on
and SHALL behave as before with the flag off.

#### Scenario: Flag on with authentication disabled

- **WHEN** the runtime starts with delegation enabled and user authentication
  disabled
- **THEN** startup fails with a clear error

### Requirement: Team-scoped requests name their team

A team-scoped execution request SHALL carry the team identifier as a required
field.

#### Scenario: Request without a team

- **WHEN** a team-scoped execution request arrives without a team identifier
- **THEN** it is rejected with a clear error before admission

### Requirement: Delegation fails closed

When delegation is enabled and the allow-list or the workload client configuration
is missing, the platform SHALL fail admission with a clear error and SHALL NOT
fall back to forwarding the person's credential.

#### Scenario: Missing allow-list with the flag on

- **WHEN** a run is admitted while the allow-list is unavailable
- **THEN** admission fails and no downstream call is made

### Requirement: A grant cannot enter from outside

The ingress SHALL reject external requests that carry grant parameters, and a
receiver SHALL ignore grant parameters from any caller not on its allow-list.

#### Scenario: External request with grant parameters

- **WHEN** a request from outside the platform carries grant parameters
- **THEN** it is refused at the ingress

### Requirement: Logs exclude identifiers

Application and security logs emitted by delegation SHALL contain no identifiers, including opaque,
hashed or synthetic account, workload, agent, team, run, request or resource
identifiers. Secret names, credentials, personal data and payloads SHALL also be
excluded. Delegation log events SHALL use bounded event, outcome and reason fields.
Required product records and request context SHALL retain the actual caller and
person. An originating worker SHALL NOT be reported as a receiver's
authenticated caller when the receiver verified the runtime's bearer.

#### Scenario: Acceptance logged without identifiers

- **GIVEN** the isolated verification environment uses mock/test identities only
- **WHEN** a receiver accepts a synthetic grant
- **THEN** the test verifies caller and person in request context and required
  product records, while every emitted log field excludes synthetic identifiers,
  token values and payloads

### Requirement: Failed workload refreshes are bounded across callers

After a failed workload-token refresh, callers sharing the provider SHALL observe
a common bounded cooldown. They SHALL fail promptly without each starting another
refresh attempt. After the cooldown, only one refresh probe SHALL run at a time;
success SHALL restore normal token acquisition. No failure SHALL expose upstream
details, return an expired credential or fall back to the person's credential.

#### Scenario: Concurrent refresh failures and recovery

- **GIVEN** concurrent delegated callers needing a token and a failing token endpoint
- **WHEN** the first refresh attempt fails
- **THEN** the waiting callers finish with a bounded failure without sequential
  network retries, and no new attempt occurs before the cooldown deadline
- **WHEN** the deadline passes and the endpoint recovers
- **THEN** one probe refreshes the token and subsequent callers reuse it

### Requirement: Children are attributed individually

A child's or team member's calls SHALL name its own agent id and the run shared
with the parent; cancelling the run SHALL cancel every child.

#### Scenario: Fan-out attribution

- **GIVEN** a parent that spawns three children
- **WHEN** each child makes a downstream call
- **THEN** each grant names that child and the shared run

### Requirement: Admission is consistent across execution surfaces

Every delegated execution surface SHALL finish workload-authenticated registration
and finalize the run's effective limits before executing. Admission time SHALL count
toward the ceiling. An admission failure SHALL unwind the local record and await
any required terminal cleanup without starting execution.

#### Scenario: OpenAI-compatible execution registers its run

- **WHEN** delegated execution enters through the OpenAI-compatible endpoint
- **THEN** its admitted provider registers exactly once before execution and the
  resolved ceiling uses the original admission start time

#### Scenario: Registration fails before compatibility execution

- **WHEN** registration fails during OpenAI-compatible admission
- **THEN** no execution starts and the local admission is cleaned up

#### Scenario: Deletion precedes registration persistence

- **GIVEN** registration has begun for an active person
- **WHEN** account deletion completes before registration acquires its lifecycle lock
- **THEN** a fresh standing check under that lock denies the write and no record is recreated

#### Scenario: Account purge races the terminal write

- **GIVEN** a run existed at the start of an end-report request
- **WHEN** account deletion purges it before the terminal write
- **THEN** the request returns 404 without recreating the record

### Requirement: Delegation logging confinement precedes request parsing

When delegation is enabled, request logging on a delegation receiver SHALL exclude
identifiers, payloads, credentials and unbounded upstream text before authentication
or body parsing. This SHALL cover body and query grants, malformed requests, errors
and redirects. Only bounded event, outcome, method, status and reason fields MAY
be logged. Feature-disabled diagnostics SHALL remain available subject to existing
sensitive-query scrubbing.

#### Scenario: Body grant is rejected before authentication

- **GIVEN** delegation is enabled and a POST body carries synthetic grant identifiers
- **WHEN** authentication or parsing fails before a principal is established
- **THEN** no log level emits identifiers, bearer claims, paths, body data or upstream detail

#### Scenario: Redirect carries sensitive text

- **WHEN** a delegation-enabled receiver returns a redirect containing a canary identifier
- **THEN** the location is absent from every emitted log field
