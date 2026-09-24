## Purpose

Defines the security profile a first-party application receives from the shared
library, and how a verified delegation grant crosses a tool mount into the route
that serves the tool call.

## ADDED Requirements

### Requirement: A first-party application receives its security profile from the shared library

The shared library SHALL build a first-party application's security
configuration from the conventional environment. The caller SHALL supply only
the names that differ between applications: the variable holding its workload
secret and the variable holding its authorization token. The result SHALL carry
the hardened profile, authorization in reader mode, and a delegation block read
from a single structured value.

An application SHALL NOT be required to restate the hardened profile, the
authorization mode, or the meaning of any shared variable. The delegation
audience SHALL come from the delegation block alone; a separate workload-audience
variable SHALL stop startup. A missing workload secret SHALL stop startup rather
than fail the first call.

#### Scenario: Two applications differ only by their own names

- **GIVEN** two installed applications
- **WHEN** each requests its security configuration
- **THEN** both receive the same profile and authorization mode, differing only
  in the workload secret and authorization token their own environment names

#### Scenario: A malformed delegation value stops startup

- **GIVEN** a structured delegation value that cannot be read
- **WHEN** the application requests its security configuration
- **THEN** startup fails
- **AND** delegation is not silently treated as disabled

#### Scenario: Delegation is off unless the deployment asks for it

- **GIVEN** no delegation value in the environment
- **WHEN** the application requests its security configuration
- **THEN** both delegation switches are off and no caller is trusted to speak for
  a person

#### Scenario: A deployment turns a direction on

- **GIVEN** a delegation value turning `accept_delegated_calls` on
- **WHEN** the application requests its security configuration
- **THEN** the application believes grants from callers holding the caller role,
  with the default caller role and audience and no list of callers

### Requirement: A browser token and a workload token may be issued by different authorities

The configuration SHALL allow the issuer that validates a person's token to
differ from the issuer that validates a workload token. When no separate
workload issuer is configured, both SHALL use the same value.

#### Scenario: One issuer serves both principals

- **GIVEN** no separate workload issuer is configured
- **WHEN** the application requests its security configuration
- **THEN** person and workload tokens are validated against the same issuer

#### Scenario: A workload token is minted where a browser token never is

- **GIVEN** a separate workload issuer is configured
- **WHEN** the application requests its security configuration
- **THEN** a person's token is validated against the address the person signed in
  at, and a workload token against the address it was minted at

### Requirement: A tool mount requires a bearer

A tool mount SHALL refuse a request that carries no bearer, and SHALL do so
without interpreting any other credential the request presents.

#### Scenario: A request carrying no bearer is refused

- **GIVEN** a tool mount on a first-party application
- **WHEN** a request arrives with no bearer, whatever else it carries
- **THEN** the request is refused as unauthenticated
- **AND** no tool is invoked

### Requirement: A grant reaches a tool mount from the endpoint alone

A tool mount SHALL read a delegation grant only from the request endpoint. The
enclosing tool-call body is content the calling model influences, so a grant
presented there SHALL NOT be read, and SHALL NOT be merged with one presented on
the endpoint.

#### Scenario: A grant on the endpoint is honoured

- **GIVEN** `accept_delegated_calls` on and a caller holding the delegation caller role
- **WHEN** it presents a grant on the tool-mount endpoint
- **THEN** the call acts for the person the grant names

#### Scenario: A grant in the tool-call body is not read

- **GIVEN** `accept_delegated_calls` on and a caller holding the delegation caller role
- **WHEN** a grant appears only in the enclosing tool-call body
- **THEN** no person is asserted from the body and no person's permissions are
  inferred from it

### Requirement: A verified grant reaches the route that serves the tool call

A tool call resolves to an ordinary route. The grant verified at the mount SHALL
reach that route, so the route authorizes the same person the mount verified.

#### Scenario: The route acts for the person the mount verified

- **GIVEN** a tool call whose mount verified a grant
- **WHEN** the tool resolves to a route
- **THEN** that route applies the named person's permissions

#### Scenario: An undelegated tool call preserves the authenticated caller

- **GIVEN** a tool call whose mount verified no grant
- **WHEN** the tool resolves to a route
- **THEN** the route receives no asserted person or delegation grant and
  evaluates the verified bearer under its ordinary endpoint authorization policy

#### Scenario: An ordinary service identity calls a tool

- **GIVEN** a valid service-role bearer without the delegation caller role and
  no grant
- **WHEN** it calls a tool on a receiver accepting delegation
- **THEN** the inner route applies that service identity's own authorization and
  eligible service-role shortcuts

### Requirement: Tool results preserve inner-route authority refusals

An inner route's authentication or permission refusal, or its structured
standing-unavailable failure, SHALL retain a bounded machine-readable authority
refusal through the tool protocol. A successful outer HTTP transport SHALL NOT
erase that refusal. A delegated client SHALL convert it into `authority_lost`
before ordinary tool-error handling, without parsing or surfacing upstream text.

#### Scenario: An inner route refuses a delegated tool call

- **GIVEN** a mounted tool whose outer bearer and grant are valid
- **WHEN** the inner route returns HTTP 403
- **THEN** the tool result preserves the authority refusal even over successful HTTP
- **AND** the delegated client stops the run and awaits descendant termination

#### Scenario: An inner standing check is unavailable

- **WHEN** an inner route returns the structured standing-unavailable HTTP 503
- **THEN** the tool protocol preserves that cause and the delegated client stops the run
- **AND** an unrelated HTTP 503 retains ordinary tool-error behavior

### Requirement: A model cannot name the person a tool call acts for

Grant parameters SHALL be absent from the tool schemas offered to a model. A
grant arriving as a tool argument SHALL be discarded before the grant verified
at the mount is applied.

#### Scenario: The grant is absent from the offered tool schemas

- **GIVEN** a tool whose route declares the grant parameters
- **WHEN** its schema is offered to a model
- **THEN** the grant parameters are absent from it

#### Scenario: A grant invented by the model never survives

- **GIVEN** a tool call carrying grant parameters among its arguments
- **WHEN** the call is served
- **THEN** those arguments are discarded
- **AND** the call asserts only the person verified at the mount; if no person
  was verified, it retains the authenticated caller without asserting a person

### Requirement: Verified tool grants are isolated per request

The bridge SHALL make a verified grant available only while its mounted request
is being served. Completion, failure and cancellation SHALL clear that context,
and concurrent calls SHALL NOT observe another call's grant.

#### Scenario: Concurrent calls represent different people

- **WHEN** two tool calls with different verified grants execute concurrently
- **THEN** each inner route receives only its own grant

#### Scenario: A call ends before another begins

- **WHEN** a mounted call completes, fails or is cancelled
- **THEN** a later undelegated request observes no grant from it

### Requirement: Applications share receiver contracts and optional tool integration

The shared package SHALL expose the security configuration builder, grant-field
declaration helper and tool-mount bridge through its public application surface.
Receiver routes SHALL declare optional grant fields in their API contracts.
Applications without tool mounts SHALL NOT require the optional tool-server
dependency; requesting that integration without the dependency SHALL report the
required package extra.

#### Scenario: Receiver route declares its grant

- **WHEN** an application applies the shared declaration helper to a route
- **THEN** its API schema exposes each optional grant field once

#### Scenario: Application does not mount tools

- **WHEN** an application imports shared security without the tool-server extra
- **THEN** ordinary security configuration and grant validation remain available
