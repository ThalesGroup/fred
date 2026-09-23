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
authorization mode, or the meaning of any shared variable.

#### Scenario: Two applications differ only by their own names

- **GIVEN** two installed applications
- **WHEN** each requests its security configuration
- **THEN** both receive the same profile and authorization mode, differing only
  in the workload identity and audience their own environment names

#### Scenario: A malformed delegation value stops startup

- **GIVEN** a structured delegation value that cannot be read
- **WHEN** the application requests its security configuration
- **THEN** startup fails
- **AND** delegation is not silently treated as disabled

#### Scenario: Delegation is off unless the deployment asks for it

- **GIVEN** no delegation value in the environment
- **WHEN** the application requests its security configuration
- **THEN** delegation is disabled and no caller is trusted to speak for a person

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

- **GIVEN** delegation enabled and an allow-listed caller
- **WHEN** it presents a grant on the tool-mount endpoint
- **THEN** the call acts for the person the grant names

#### Scenario: A grant in the tool-call body is not read

- **GIVEN** delegation enabled and an allow-listed caller
- **WHEN** a grant appears only in the enclosing tool-call body
- **THEN** the call acts for nobody and no person's permissions are applied

### Requirement: A verified grant reaches the route that serves the tool call

A tool call resolves to an ordinary route. The grant verified at the mount SHALL
reach that route, so the route authorizes the same person the mount verified.

#### Scenario: The route acts for the person the mount verified

- **GIVEN** a tool call whose mount verified a grant
- **WHEN** the tool resolves to a route
- **THEN** that route applies the named person's permissions

#### Scenario: An undelegated tool call names nobody

- **GIVEN** a tool call whose mount verified no grant
- **WHEN** the tool resolves to a route
- **THEN** the route acts for nobody, and the calling workload receives no
  authority of its own

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
- **AND** the call acts for the person verified at the mount, or for nobody when
  the mount verified none
