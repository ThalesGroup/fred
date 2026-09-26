## Purpose

Define what an authorization denial reports, so that a denial caused by a
person's organization standing, a denial caused by an ordinary missing
permission, and a denial caused by an unreachable authorization dependency can
be told apart by an operator and are classified correctly by transport status,
without disclosing who was denied or what they were denied.

## ADDED Requirements

### Requirement: A denial preserves the cause the decision produced

An authorization denial SHALL carry, from the point it is raised to the point it
is reported, whether the authorization dependency reached a decision or could
not be consulted. A handler SHALL NOT discard that distinction. HTTP responses
SHALL expose a bounded machine-readable cause so clients do not classify a
standing failure by parsing its human-readable detail.

#### Scenario: The dependency answered and refused

- **WHEN** the authorization dependency evaluates a person's access and returns
  a refusal
- **THEN** the denial is reported as a decided refusal
- **AND** the report distinguishes a refusal on organization standing from a
  refusal on a missing permission

#### Scenario: The dependency is already gone when its client is established

- **WHEN** a standing check cannot reach the authorization dependency while
  establishing its client, before any check has been sent
- **THEN** the denial is reported as undecided, the same as a check that was
  sent and could not be answered
- **AND** the report carries no detail of the underlying transport failure

#### Scenario: The dependency could not be consulted

- **WHEN** the authorization dependency is unreachable, times out, or otherwise
  cannot produce a standing decision
- **THEN** the denial is reported as undecided rather than as a refusal
- **AND** access is still refused, so the request fails closed

### Requirement: An undecided denial is classified as a server-side failure

A denial marked unavailable because the authorization dependency could not be
consulted SHALL be reported to the caller with HTTP 503. A decided standing or
permission refusal SHALL use HTTP 403.

#### Scenario: A dependency outage reaches a caller

- **WHEN** a request receives a standing denial marked unavailable because the
  authorization dependency could not be consulted
- **THEN** the response status is HTTP 503
- **AND** availability monitoring that counts server-side failures observes it

#### Scenario: A decided refusal reaches a caller

- **WHEN** a request is refused because the dependency decided the person lacks
  access
- **THEN** the response status is HTTP 403

#### Scenario: Runtime admission cannot establish standing

- **GIVEN** a native or compatibility execution request for a direct or managed target
- **WHEN** its standing check is unavailable
- **THEN** admission returns HTTP 503 with the bounded standing-unavailable cause
- **AND** no run starts and no handler converts the outage into a permission denial

#### Scenario: A control-plane request cannot establish standing

- **WHEN** a control-plane operation receives an unavailable standing decision
- **THEN** its response preserves HTTP 503 and the same machine-readable cause
- **AND** its denial log and standing audit contain only bounded fields

### Requirement: A denial log line carries the fields that separate its causes

Each denial SHALL emit one log record carrying the subject type, the attempted
action, the resource type, and whether the decision was reached or the
dependency was unavailable. The record SHALL NOT contain a person identifier, a
team identifier, a resource identifier, a credential, or any part of one.

#### Scenario: Three denials with different causes are compared

- **WHEN** one request is refused on standing, a second on a missing permission,
  and a third because the dependency was unavailable
- **THEN** the three records differ in the fields naming the cause
- **AND** no record contains an identifier for the person, the team or the
  resource

#### Scenario: A record is inspected for sensitive content

- **WHEN** any denial record is emitted
- **THEN** it contains no credential, token, secret, or fragment of one

### Requirement: The caller-facing detail is bounded and does not overstate

The detail returned to the caller SHALL distinguish a standing refusal from a
permission refusal, SHALL NOT name the person, team or resource involved, and
SHALL NOT assert a cause the platform did not establish.

#### Scenario: A person without current standing is refused

- **WHEN** a person whose organization standing is not active is refused
- **THEN** the detail conveys that the account's standing prevents the request
- **AND** it names no person, team or resource

#### Scenario: A person with standing lacks a permission

- **WHEN** a person holding active standing is refused for a missing permission
- **THEN** the detail conveys a permission refusal
- **AND** it does not suggest the account's standing was the cause

#### Scenario: The dependency was unavailable

- **WHEN** the refusal arises from an unavailable dependency
- **THEN** the detail does not claim the person lacks access

### Requirement: A standing refusal is recorded as an audit event

A refusal caused by a person's organization standing SHALL emit an audit event
on the same audit surface that records delegation grant decisions, carrying the
outcome and the reason, and carrying no person identifier.

#### Scenario: A standing refusal is audited

- **WHEN** a request is refused because the person's standing is not active
- **THEN** an audit event records the refusal with its outcome and reason
- **AND** the event carries no person identifier

#### Scenario: A permission refusal is not audited as a standing refusal

- **WHEN** a request is refused for a missing permission while standing is
  active
- **THEN** no standing refusal audit event is emitted
