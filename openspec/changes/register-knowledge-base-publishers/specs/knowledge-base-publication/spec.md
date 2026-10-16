## Purpose

Decides who may declare a Knowledge Base to Fred and under which prefix: only clients the
operator registered, each within the prefix the operator assigned to it.

## ADDED Requirements

### Requirement: Publishers are registered by the operator

The Control Plane configuration SHALL list the clients allowed to publish Knowledge Base
definitions, each with the one prefix it owns. The list SHALL be empty by default. A
publication by a client absent from the list SHALL be refused with HTTP 403, and the
refusal SHALL name the client and the setting to change.

#### Scenario: Unlisted client

- **WHEN** a service identity whose client is not in `knowledge_bases.publishers` publishes
  a definition
- **THEN** the Control Plane answers 403, stores nothing, and the message names the client
  and `knowledge_bases.publishers`

#### Scenario: Default configuration

- **WHEN** the configuration sets no publishers and any client publishes
- **THEN** the publication is refused

### Requirement: A publisher writes only under its registered prefix

A listed client SHALL publish only definitions under its registered prefix, using the same
segment-boundary rule as dispatch (`prefix_covers`). The prefix carried by the publication
request SHALL equal the registered one.

#### Scenario: Declaration outside the prefix

- **WHEN** `kb-fred.samples`, registered with `fred.samples`, publishes `other.webdav`
- **THEN** the publication is refused with 403 and nothing is stored

#### Scenario: Claimed prefix differs

- **WHEN** a listed client publishes with a request prefix other than its registered one
- **THEN** the publication is refused with 403

#### Scenario: Registered publisher

- **WHEN** `kb-fred.samples` publishes `fred.samples.webdav` with prefix `fred.samples`
- **THEN** the definition is stored and stays unusable until a platform admin enables it for
  a team

### Requirement: Registrations do not overlap

The configuration SHALL be refused at startup when two entries register the same prefix,
or when one registered prefix covers another, so that one name is never publishable by
two clients.

#### Scenario: Overlapping prefixes

- **WHEN** the configuration registers `fred` for one client and `fred.samples` for another
- **THEN** the Control Plane refuses to start and names both entries

### Requirement: A user session never publishes

Publication SHALL keep requiring a service identity: a listed `client_id` SHALL NOT make a
person's session a publisher.

#### Scenario: Person's token for a listed client

- **WHEN** a token without a service identity carries a listed client in `azp`
- **THEN** the publication is refused with 403
