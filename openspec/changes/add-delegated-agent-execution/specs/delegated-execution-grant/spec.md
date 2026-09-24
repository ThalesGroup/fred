## Purpose

Defines how an agent run identifies the person it acts for after local admission,
how receiving services authenticate and authorize the calling workload's
statement, how a run ends with its response or on a typed stop, and the
operational signals delegation emits. Execution lifecycle, typed-stop and
execution-diagnostic requirements cover ReAct and DeepAgent runs and their
supported child agents.

## ADDED Requirements

### Requirement: The person's credential is never retained for execution

With `act_for_people` on, the platform SHALL use the person's access token only
for local admission. The platform SHALL NOT retain the person's token beyond
authenticating that request, store it in run state, forward, exchange or renew
it. No outbound call made for the run SHALL carry it.

#### Scenario: The person's token expires during the run

- **GIVEN** a run admitted with a valid token, `act_for_people` on, current person
  authorization and available downstream services
- **WHEN** that token expires while the run is still working
- **THEN** downstream calls made for the run continue to succeed

#### Scenario: Outbound requests never carry the person's bearer

- **GIVEN** `act_for_people` on
- **WHEN** any downstream call is made for the run
- **THEN** its authorization header carries the platform's workload token and not
  the person's token

### Requirement: Every delegated call authenticates its caller and identifies its subject

A delegated call SHALL carry the platform's workload credential and a delegation
grant made of the request parameters `person`, `run` and `agent`. A receiver
SHALL establish no asserted person without a complete verified grant and SHALL
apply the authenticated caller's ordinary endpoint policy. A receiver
that accepts delegated calls SHALL refuse with 403 `delegation_not_allowed` a
complete grant presented by a bearer without the delegation caller role, SHALL
audit the refusal without the grant's values, and SHALL build no subject from it.
To find such a grant it SHALL inspect the query string of every caller and the
JSON body of a service identity only, never on a tool mount; a person's body
SHALL NOT be read for a grant.

#### Scenario: Grant without a role-holding bearer

- **GIVEN** a receiver that accepts delegated calls
- **WHEN** a complete grant arrives in the query string with a valid bearer that
  does not carry the delegation caller role
- **THEN** the request is refused with 403 `delegation_not_allowed`, the refusal
  is audited without the grant's values, and no subject is built

#### Scenario: Partial grant without a role-holding bearer

- **WHEN** incomplete grant parameters arrive with a valid bearer that does not
  carry the delegation caller role
- **THEN** the parameters are ignored, no person is asserted, and the ordinary
  authenticated caller policy applies

#### Scenario: Bearer without a grant

- **GIVEN** a valid workload bearer carrying the delegation caller role
- **WHEN** no grant parameters accompany it
- **THEN** no person is asserted and the request is decided on the calling
  workload's ordinary endpoint policy

### Requirement: A grant is accepted only as a role-holding caller's statement

A receiver SHALL accept the grant parameters as the caller's statement only when
the accompanying access token is valid, comes from the receiver's realm under
either of its configured addresses, is addressed to the configured delegation
audience, carries the configured caller role at the configured claim path, and
was not issued to a client people sign in through: the receiver's own user client
or one the delegation block lists. A receiver configured to trust service-account
tokens only SHALL also require the identity provider's service-account markers.
An `azp` claim alone SHALL NOT establish that trust. The person SHALL be an
immutable subject identifier in the configured realm, not an email or username.
The grant SHALL have no lifetime of its own, SHALL be presented on every call
including retries, and a receiver SHALL NOT forward it to another service.

#### Scenario: Statement from a workload without the caller role

- **GIVEN** a receiver that accepts delegated calls
- **WHEN** a complete grant arrives with a valid bearer that does not carry the
  caller role at the configured claim path
- **THEN** the request is refused and no subject is built

#### Scenario: A service identity's grant in a body is refused

- **GIVEN** a receiver that accepts delegated calls, outside a tool mount
- **WHEN** a service identity without the caller role presents a complete grant in
  a JSON body
- **THEN** the request is refused, while a person's body is never read for a grant

#### Scenario: Token issued to a client people sign in through

- **GIVEN** a valid token issued to a client people sign in through, even one
  carrying the caller role or a service role
- **WHEN** it carries delegation parameters
- **THEN** it cannot establish a delegated subject or invoke delegated operations

#### Scenario: Service-account tokens only

- **GIVEN** a receiver configured to trust service-account tokens only
- **WHEN** a person's token carrying the caller role arrives from a client that is
  not listed as a client people sign in through
- **THEN** it cannot establish a delegated subject, while a token the identity
  provider issued to a workload client's own service account still can

#### Scenario: Role-holding token not addressed to delegation

- **GIVEN** a valid token carrying the caller role but not addressed to the
  delegation audience
- **WHEN** it carries delegation parameters
- **THEN** delegation is refused with 403

#### Scenario: Malformed grant

- **WHEN** the parameters are incomplete or malformed
- **THEN** no person is asserted from those parameters

#### Scenario: Parameters split across transports

- **WHEN** part of a grant arrives in the query string and the rest in the body,
  or the grant arrives form-encoded or inside tool arguments
- **THEN** the parameters are not a grant

#### Scenario: A call outlives the bearer

- **GIVEN** a call accepted with a valid bearer and grant
- **WHEN** the bearer expires while the receiver is still processing the call
- **THEN** the call completes and its result is returned

### Requirement: Receivers trust workloads and apply the person's permissions

Each receiver SHALL trust a workload by the caller role in its verified token,
without a per-receiver list of callers, and SHALL apply the asserted person's
function, object, field and team permissions. Administrative actions SHALL retain
their normal user authorization. Explicit own-credential guards SHALL remain in
force. Receivers SHALL make these checks locally without consulting the control
plane for a credential or delegation decision.

Delegation configuration SHALL provide one switch per direction, both off by
default: `act_for_people` for outgoing calls made during a person's run and
`accept_delegated_calls` for believing grants. It SHALL name the delegation
audience, the caller role and its claim path, with defaults. The caller role
SHALL be read from a verified token whatever the switches; only believing a grant
SHALL depend on `accept_delegated_calls`. Unknown configuration fields, including
per-caller lists, SHALL be rejected, and a single `enabled` switch SHALL be
refused with an error naming both directions.

With `act_for_people` off, an authenticated person's outbound calls SHALL use
the person's bearer through the live token provider and SHALL send no delegation
grant. Children SHALL observe updates to that provider on subsequent calls.

#### Scenario: A single switch is refused

- **WHEN** a configuration sets `security.delegation.enabled`
- **THEN** startup fails with an error naming `act_for_people` and
  `accept_delegated_calls`

#### Scenario: Acting for people alone believes no grant

- **GIVEN** a backend with `act_for_people` on and `accept_delegated_calls` off
- **WHEN** a caller holding the delegation caller role presents a valid grant
- **THEN** no person is asserted and the grant is not believed

#### Scenario: Outgoing delegation is disabled

- **GIVEN** `act_for_people` off and a person executing with a live token provider
- **WHEN** the provider receives an updated token before a parent or child call
- **THEN** that call uses the updated person's bearer and sends no delegation grant

#### Scenario: Trusted workload acts for an authorized person

- **GIVEN** a valid trusted workload, a valid grant and an authorized person
- **WHEN** it invokes a delegation-capable endpoint
- **THEN** delegation succeeds and the endpoint applies the person's permissions

#### Scenario: Delegated action targets unauthorized data

- **GIVEN** a trusted workload acting for a person
- **WHEN** it targets an action, object, field or team outside the person's
  permissions
- **THEN** access is denied without a partial write or protected data disclosure

#### Scenario: Workload role cannot authorize an administrative action for a person

- **GIVEN** a trusted workload whose service account has privileged roles
- **WHEN** its asserted person lacks the endpoint's administrative permission
- **THEN** access is denied based on the person's authorization

### Requirement: Only the run record names the person

The `person` and `run` parameters SHALL come from the local record written at
admission. The `agent` parameter SHALL identify the executing agent established
by the runtime, including a child's own identity on the shared run. No execution
request argument, tool input or model output SHALL override those identities.
A run with a missing or terminal record SHALL obtain no delegated credential or
start a delegated call, including when token acquisition is already awaiting a
renewal as the run ends.

#### Scenario: Call without a record

- **WHEN** a delegated call is attempted for a run id that has no admission record
- **THEN** no call is made

#### Scenario: Tool input cannot name a subject

- **GIVEN** a tool call whose arguments contain a user identifier
- **WHEN** the runtime makes the downstream call
- **THEN** the grant names the admitted person, not the identifier in the arguments

#### Scenario: Run ends during workload-token acquisition

- **GIVEN** credential acquisition is waiting for the workload token
- **WHEN** the run ends before acquisition returns
- **THEN** no credential is returned for that run and no outbound request starts

### Requirement: An asserted person is distinct from an authenticated one

A principal built from a grant SHALL be a distinct kind, SHALL never carry any
role, and SHALL be rejected by any endpoint with an explicit guard requiring the
directly authenticated caller. The runtime endpoint inventory in
[the design](../../design.md#own-credential-endpoints) SHALL enforce these guards.

#### Scenario: Service-role shortcuts do not apply

- **GIVEN** a principal built from a grant
- **WHEN** a service-role check is evaluated on it
- **THEN** the check is false

#### Scenario: Own-credential runtime guard rejects a delegated person

- **GIVEN** a trusted workload and a valid user grant
- **WHEN** it calls a runtime endpoint listed as requiring the caller's own
  credential
- **THEN** the request is rejected before protected work, including on the
  OpenAI-compatible chat endpoint

### Requirement: Permission checks are live on the asserted person

A receiver SHALL evaluate the same permission checks for an asserted person as
for an authenticated one, against current relations, on every call.

#### Scenario: Permission removed mid-run

- **GIVEN** a run acting for a person
- **WHEN** the person's team permission is removed
- **THEN** the next call for that run is denied

### Requirement: A run stops on a typed reason

The terminal error event SHALL carry an optional `reason` with the values
`authority_lost`, `cancelled` and `delegation_unavailable`, absent for an ordinary
crash. When a receiver denies a delegated call for lost authority (401 or 403),
or returns a structured standing-unavailable refusal (503), the run SHALL end
with reason `authority_lost`. Unrelated 503 responses SHALL retain ordinary
error handling. A local per-tool permission or standing refusal during delegated
execution SHALL produce the same typed stop. When delegation cannot be used —
no workload credential, a refused tool server — the run SHALL end with
`delegation_unavailable`. A stopped run's message SHALL be a bounded
platform-owned sentence chosen from the reason, with no upstream detail. A stopped
call SHALL NOT be retried, SHALL NOT be retried under the platform's own identity,
and SHALL NOT be turned into tool text for the model, including through a
capability's own error handling.

#### Scenario: Denied mid-run

- **WHEN** a downstream call returns an authorization failure
- **THEN** the run ends with reason `authority_lost`, all children are cancelled,
  and no further execution, tool or data call is made for the run

#### Scenario: A local tool recheck refuses authority

- **GIVEN** a delegated run that passed admission
- **WHEN** a local per-tool authorization recheck refuses permission or standing, or cannot establish standing
- **THEN** the tool handler is not called and the run ends with `authority_lost`
- **AND** ordinary execution without delegated credentials retains its existing authorization error behavior

#### Scenario: Upstream detail is not exposed

- **GIVEN** an upstream error body containing a marker string
- **WHEN** the run ends for lost authority
- **THEN** the marker appears in no event, transcript, log, trace or checkpoint

#### Scenario: A capability does not answer a stop with text

- **GIVEN** a capability tool that turns its own failures into text for the model
- **WHEN** its downstream call loses authority
- **THEN** the stop escapes the tool and the run ends with `authority_lost`

### Requirement: A stop ends the whole run and the run has no platform limit

Each run SHALL have one scope holding its children and its recorded stop; a
nested run SHALL join its parent's scope and a closed scope SHALL NOT be joined.
Once a stop is recorded, no further step SHALL start, parallel siblings SHALL be
cancelled, a stopped child SHALL end its parent on the same reason, and the root
SHALL emit exactly one terminal event. External cancellation SHALL NOT produce a
synthetic stop event. Delegation SHALL impose no wall-clock limit on a run, no
bound on its concurrent children, no cap on concurrently admitted runs and no
age-based expiry of a live record. Existing per-call timeouts and engine step
limits SHALL remain applicable.

#### Scenario: A stopped child stops its siblings and its parent

- **GIVEN** a run with several children working in parallel
- **WHEN** one child stops with `authority_lost`
- **THEN** its siblings are cancelled and the parent ends with one terminal event
  carrying `authority_lost`

#### Scenario: A run starts every child its turn asks for

- **WHEN** a turn asks for more children at once than any fixed bound would allow
- **THEN** every child starts and runs concurrently

#### Scenario: A long run keeps its grant

- **GIVEN** a delegated run admitted long ago and still working
- **WHEN** the pod admits another run
- **THEN** the first run still obtains its grant on its next call

#### Scenario: Concurrent run admission

- **GIVEN** available runtime capacity and 128 active admitted runs
- **WHEN** another authorized run is admitted
- **THEN** delegation accepts the run and all active runs retain their records

#### Scenario: An abandoned run does not affect the next

- **GIVEN** a run whose stream was abandoned after a stop was recorded
- **WHEN** a new run starts on the same pod
- **THEN** it opens its own scope and inherits no stop

### Requirement: A delegated run lives exactly as long as its response

A delegated attended run SHALL be owned by the response that admitted it on both
streaming APIs. On normal completion, human pause, detected disconnect, request
cancellation or response failure, including before the first frame, the runtime
SHALL prevent further credential acquisition before asynchronous teardown,
cancel and await its execution tasks and descendants, close its complete stream
chain and discard its admission record before response handling finishes.
Cleanup SHALL remain effective when cancellation occurs during an asynchronous
cleanup operation and SHALL be idempotent.

Only the run's end SHALL discard its record; its age SHALL NOT remove it. Stream
routes SHALL emit `data:` frames without a reconnect handle. A human pause SHALL
end the stream after `awaiting_human`; the answer SHALL receive fresh admission.
An ended run SHALL leave no delegated admission record. An interrupted turn
SHALL NOT produce completed-turn history or completion metrics. Connection loss
SHALL trigger termination when detected by the server; immediate detection of
sleep, power loss or network failure is not guaranteed.

#### Scenario: Stream closes mid-run

- **GIVEN** a delegated run with a child still working
- **WHEN** its stream closes before the run finishes
- **THEN** the run obtains no further credential, its execution and child tasks
  have ended, its iterators are closed and its record is gone when response
  handling finishes

#### Scenario: The response ends before its first frame

- **WHEN** a delegated response is dropped, cancelled or fails before its first
  frame is sent
- **THEN** its run record is gone when the response ends

#### Scenario: A send that never completes

- **WHEN** the request is cancelled while a frame waits to be sent
- **THEN** the run ends, its children are cancelled and its record is discarded

#### Scenario: Response sending fails

- **GIVEN** either streaming API, including a transport using ASGI 2.4 send errors
- **WHEN** sending response headers or a body frame raises
- **THEN** response cleanup ends execution and descendants, closes the iterator
  chain and releases the record without depending on a success callback

#### Scenario: Cancellation during asynchronous cleanup

- **GIVEN** iterator disposal or descendant cleanup is waiting asynchronously
- **WHEN** the request is cancelled while cleanup is in progress
- **THEN** cleanup still completes, all owned tasks have ended and the record is
  absent before response handling returns

#### Scenario: Completion or pause with a child still running

- **GIVEN** a registered child remains active when the root completes or pauses
- **WHEN** teardown begins
- **THEN** the child cannot obtain credentials, its cancellation and cleanup are
  awaited, and no owned task remains when response handling finishes

#### Scenario: Cleanup is entered repeatedly

- **WHEN** iterator ownership and response ownership both trigger cleanup
- **THEN** the run ends safely, its resources are released and other runs remain
  unaffected

#### Scenario: A human pause ends the stream and the answer is a new run

- **GIVEN** a delegated run that asks the person for input
- **WHEN** it emits `awaiting_human`
- **THEN** the stream ends and the run's record is discarded, and the person's
  answer is admitted as a new run with their current token

#### Scenario: A dropped stream is not requested again

- **GIVEN** the chat client streaming a turn
- **WHEN** the stream drops
- **THEN** the client reports the drop once and sends no second request for the
  turn

#### Scenario: Page ownership ends

- **WHEN** the chat component unmounts or the person intentionally interrupts its
  accepted stream
- **THEN** the client aborts that request, sends no reconnect request and reports
  no error for the intentional abort

### Requirement: Admission is local and consistent across execution surfaces

Every delegated execution surface, the OpenAI-compatible one included, SHALL
admit a run through the same local admission before executing: it SHALL write
the pod-local run record and check the person there. For a managed target it
SHALL resolve the binding through the control plane's read-only runtime-binding
lookup with the workload bearer and the grant, and the control plane SHALL
authorize that lookup for the asserted person. Admission of a direct target SHALL
make no control-plane call. Admission SHALL record the run only inside the pod. An admission
failure SHALL discard the local record without starting execution.

#### Scenario: OpenAI-compatible execution admits its run locally

- **WHEN** delegated execution enters through the OpenAI-compatible endpoint
- **THEN** its run record is written before execution, admission makes no
  control-plane call, its outbound calls carry the workload bearer, and the record is discarded
  when the response ends

#### Scenario: A delegated managed run resolves its binding

- **WHEN** a delegated run targets a managed agent instance
- **THEN** the runtime makes one read-only runtime-binding lookup carrying its
  workload bearer and the `person`, `run` and `agent` parameters, and no other
  control-plane call for admission

#### Scenario: A delegated direct run

- **WHEN** a delegated run targets an agent template directly
- **THEN** admission makes no control-plane call

#### Scenario: A refused binding lookup leaves no record

- **WHEN** the runtime-binding lookup of a delegated managed run is refused
- **THEN** no execution starts and no run record remains on the pod

### Requirement: Tool servers authenticate by declared mode

For a run using delegated credentials, the runtime SHALL send the workload bearer and the
grant, outside tool arguments, to a server declared `delegated`, SHALL send no
credential to a server declared `no_token`, and SHALL refuse to activate any other
server, or a `delegated` server whose transport cannot carry the grant, with
reason `delegation_unavailable`. A connection carrying a grant SHALL NOT be shared
with another run. A tool server refusing a delegated call or listing SHALL end
the run with `authority_lost` without a retry.

An ordinary service identity running as itself SHALL retain its own bearer and
send no grant, including to a server declared `delegated`, while a `no_token`
server SHALL receive no credential. Authentication mode restrictions SHALL be
evaluated for the execution's credential type.

#### Scenario: User-token server under delegation

- **GIVEN** a run using delegated credentials and a server declared `user_token`
- **WHEN** the run activates its tools
- **THEN** activation fails with reason `delegation_unavailable` and no bearer is
  sent

#### Scenario: Delegated server

- **GIVEN** a run using delegated credentials and a server declared `delegated`
- **WHEN** a tool is called
- **THEN** the call carries a current workload bearer and the grant on the
  endpoint, never among the tool's arguments

#### Scenario: Service identity uses a delegated catalog entry

- **GIVEN** outgoing delegation is enabled, a service identity without the caller
  role and a server declared `delegated`
- **WHEN** the service identity's agent run calls the tool
- **THEN** the request carries that service identity's bearer and no grant

### Requirement: The workload token is accepted by every receiver

A workload token issued to the agent backend or to an installed application
SHALL authenticate without modification at its intended receiving services when
signature, allowed algorithm, trusted issuer and key source, validity,
access-token purpose and audience checks pass. Under strict audience validation a
receiver SHALL accept the delegation audience in place of its login audience only
for a token that carries the caller role, was not issued to a client people sign
in through and, when the receiver trusts service-account tokens only, bears the
service-account markers. Successful authentication SHALL NOT bypass the
caller-role check or the person's authorization. Shared deployments SHALL enforce
strict issuer and audience validation.

#### Scenario: Accepted under strict audience validation

- **GIVEN** a receiver validating audiences
- **WHEN** a call arrives with the agent backend's workload token, addressed to
  the delegation audience and carrying the caller role
- **THEN** the token is accepted and the caller is identified as the agent
  backend's client

#### Scenario: Delegation audience without the caller role

- **GIVEN** a receiver validating audiences
- **WHEN** a token addressed only to the delegation audience lacks the caller role
- **THEN** the receiver rejects it

#### Scenario: Invalid token context

- **WHEN** a request presents a token with a wrong issuer, audience, purpose,
  signature, algorithm, key source or validity period
- **THEN** the receiver rejects it before trusting delegation parameters

### Requirement: Deployment protects delegated transport and credentials

Delegated traffic and its token, key-discovery and authorization dependencies
SHALL use authenticated encrypted transport without plaintext fallback. Workload
secrets SHALL be stored in the deployment's managed secret facility with
restricted access. Workload clients SHALL enable only required service-account
flows and SHALL be separate from user-facing clients. These controls SHALL use
existing identity-provider, transport and secret-management mechanisms, without
custom grant cryptography.

#### Scenario: Untrusted transport peer

- **WHEN** a delegated dependency presents an untrusted certificate or a
  connection would fall back to plaintext
- **THEN** the connection fails without sending credentials or delegation data

#### Scenario: Workload client requested through a user flow

- **WHEN** a user authorization or password flow is requested for a delegation
  workload client
- **THEN** the identity provider refuses it and issues no delegation-capable token

### Requirement: Delegation requires user authentication

`act_for_people` SHALL be honoured only when user authentication is enabled; with
authentication disabled the runtime SHALL refuse to start with it on. A runtime
SHALL also refuse to start when it accepts delegated calls without acting for
people.

#### Scenario: Acting for people with authentication disabled

- **WHEN** the runtime starts with `act_for_people` on and user authentication
  disabled
- **THEN** startup fails with a clear error

#### Scenario: Accepting delegated calls without acting for people

- **WHEN** the runtime starts with `accept_delegated_calls` on and
  `act_for_people` off
- **THEN** startup fails with a clear error

### Requirement: Managed execution requests name their team

A managed execution request SHALL carry `runtime_context.team_id` as a required,
non-blank field of the request schema; a direct template request SHALL keep its
team optional.

#### Scenario: Managed request without a team

- **WHEN** a managed execution request arrives without a team identifier
- **THEN** it is rejected with a clear error before admission

### Requirement: Delegation fails closed

When `act_for_people` is on and the workload client configuration is missing or
its token cannot be obtained, the platform SHALL fail admission or end the run
with `delegation_unavailable` and SHALL NOT fall back to forwarding the person's
credential.

#### Scenario: Missing workload client with act_for_people on

- **WHEN** a run is admitted while no workload credential is configured
- **THEN** admission fails, no run record is kept and no downstream call is made

### Requirement: A grant cannot enter from outside

The ingress SHALL reject external requests that carry grant parameters. A
receiver SHALL build no subject from grant parameters presented by a caller
without the caller role.

#### Scenario: External request with grant parameters

- **WHEN** a request from outside the platform carries grant parameters
- **THEN** it is refused at the ingress

### Requirement: Logs exclude identifiers

Application and security logs emitted by delegation SHALL contain no identifiers,
including opaque, hashed or synthetic account, workload, agent, team, run,
request or resource identifiers. Secret names, credentials, personal data and
payloads SHALL also be excluded. Delegation log events SHALL use bounded event,
outcome and reason fields. Required product records and request context SHALL
retain the actual caller and person. An originating worker SHALL NOT be reported
as a receiver's authenticated caller when the receiver verified the runtime's
bearer.

#### Scenario: Acceptance logged without identifiers

- **GIVEN** a verification environment using synthetic identities only
- **WHEN** a receiver accepts a synthetic grant
- **THEN** caller and person are present in request context and required
  product records, while every emitted log field excludes the synthetic
  identifiers, token values and payloads

#### Scenario: A failed delegated turn is logged without identifiers

- **WHEN** a delegated turn's stream or history write fails
- **THEN** the log carries bounded event, outcome and reason fields and no
  identifier or exception text

### Requirement: Delegation logging confinement precedes request parsing

When either delegation switch is on, request logging SHALL exclude identifiers,
payloads, credentials and unbounded upstream text before authentication or body
parsing. This SHALL cover query and body grants, malformed requests, errors and
redirects. Only bounded event, outcome, method, status and reason fields SHALL be
logged for a request carrying a grant. With both switches off, request
diagnostics SHALL remain available subject to existing sensitive-query scrubbing.

#### Scenario: Body grant is rejected before authentication

- **GIVEN** either delegation switch is on and a POST body carries synthetic grant
  identifiers
- **WHEN** authentication or parsing fails before a principal is established
- **THEN** no log level emits identifiers, bearer claims, paths, body data or
  upstream detail

#### Scenario: Redirect carries sensitive text

- **WHEN** a backend with either switch on returns a redirect containing a canary
  identifier
- **THEN** the location is absent from every emitted log field

#### Scenario: Access log of a delegated request

- **GIVEN** either delegation switch is on
- **WHEN** a request carrying grant parameters is logged by the access log
- **THEN** the record carries only the method and status of a delegated request

### Requirement: Workload acquisition failures preserve safe retry behavior

Workload-token acquisition SHALL remain synchronized by the provider lock.
After an acquisition failure, the next caller MAY retry immediately. Successful
acquisition SHALL populate the cache for subsequent callers. An unreachable token
endpoint SHALL surface as a transport error of the same class so existing
polling callers can retry. Failures SHALL NOT expose upstream details or secret
names, return expired credentials or fall back to the person's credential.

#### Scenario: Recovery after a failed acquisition

- **GIVEN** a provider whose previous token request failed
- **WHEN** the endpoint recovers and another caller requests a token
- **THEN** acquisition is attempted immediately and the successful token is cached

#### Scenario: A poller survives an unreachable token endpoint

- **GIVEN** a document publisher waiting for processing to complete
- **WHEN** the token endpoint cannot be reached during polling
- **THEN** the transport error preserves the caller's existing retry behavior

### Requirement: Children are attributed individually

A child's or team member's calls SHALL name its own agent id and the run shared
with the parent; a child SHALL receive the live credential provider rather than a
copied credential; cancelling the run SHALL cancel every child.

#### Scenario: Fan-out attribution

- **GIVEN** a parent that spawns three children
- **WHEN** each child makes a downstream call
- **THEN** each grant names that child and the shared run

### Requirement: Workload token acquisition and delegation decisions are observable

Each backend SHALL export, without identity, URL, client, team, token or run
labels: workload token requests to the identity provider by operation (`initial`
for a provider's first token, `renewal` afterwards) and outcome (`success`,
`error`, `cancelled`) with their latency; the caller's total wait for a token;
token cache decisions (`hit`, `miss`, `shared_refresh`); and grant
admission decisions by outcome and bounded reason. Every known series SHALL exist
at zero before traffic. A failing metrics observer SHALL NOT affect token
acquisition.

#### Scenario: Initial acquisition, reuse and renewal

- **GIVEN** a workload token provider with no token
- **WHEN** it acquires a token, serves a second caller from its cache, and later
  replaces the token before expiry
- **THEN** one `initial` request, one cache hit and one `renewal` request are
  recorded, and the export contains no identifier

#### Scenario: Metrics failure

- **WHEN** the metrics observer raises
- **THEN** the caller still receives its token

### Requirement: An execution error reaches the person without internal detail

An unhandled execution error SHALL reach the person as a fixed sentence chosen by
the phase that failed, or the sentence of an error that owns a user-facing
message, followed by a random support reference. The runtime SHALL log the same
reference with exception types and code locations only — file name, line and
function, across bounded chains and groups of exceptions — and SHALL NOT log or
surface exception messages, URLs, variables or source lines.

#### Scenario: A support reference joins the answer to the log

- **WHEN** a turn fails with an unhandled error whose message holds a token
- **THEN** the person sees a fixed sentence and a support reference, the log
  carries the same reference and the error's type and location, and neither
  carries the token

### Requirement: A local delegation overlay only turns switches on

A backend SHALL read a local delegation file only when its local run targets name
one explicitly. The file SHALL only turn `act_for_people` or
`accept_delegated_calls` on over the selected configuration's delegation block,
and SHALL be refused when its issuer is not a realm address of that configuration
or its audiences lack the configured delegation audience. A named file that is
missing or malformed SHALL stop startup.

#### Scenario: The overlay keeps every other setting

- **GIVEN** a configuration whose delegation block sets a caller role and
  audience
- **WHEN** a local file turns `accept_delegated_calls` on
- **THEN** only that switch changes and every other delegation setting is the
  configuration's

#### Scenario: A mismatched overlay is refused

- **WHEN** a local file names an issuer or audience the selected configuration
  does not trust
- **THEN** the backend refuses to start

### Requirement: Worker startup and shared task contracts remain independent of attended execution

The local control-plane worker command SHALL select its worker configuration.
The knowledge backend SHALL refuse startup when user authentication is enabled
and its required authentication client secret is absent. Existing task
persistence, cancellation, event replay and scheduled knowledge-processing
contracts SHALL remain independent of attended agent execution. The control-plane
scheduler connection log SHALL exclude endpoint and namespace identifiers.

#### Scenario: Control-plane worker starts locally

- **WHEN** the local worker command is invoked
- **THEN** the worker loads the designated worker configuration

#### Scenario: Required backend credential is absent

- **GIVEN** user authentication is enabled at the knowledge backend
- **WHEN** its required client secret is absent
- **THEN** startup fails before the backend serves requests

#### Scenario: Existing scheduled task executes

- **WHEN** an existing non-agent task is persisted, replayed, cancelled or run by
  its worker
- **THEN** it follows its established task contract without an attended-agent
  admission or response dependency
