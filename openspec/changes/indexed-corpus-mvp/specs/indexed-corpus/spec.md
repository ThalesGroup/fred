## Purpose

Defines the observable contract for pulling external data into FRED as an indexed corpus: which corpus types a team may use, what a created corpus instance guarantees about its own scope and content identity, and how a source connector's discovered changes must behave so synchronization never duplicates, loses, or silently corrupts work.

## ADDED Requirements

### Requirement: A corpus type is registered platform-wide, not created per team
A corpus type (its pipeline kind, push/pull mode, and — for pull — its connector kind) SHALL be defined once for the whole deployment, never authored or duplicated by an individual team.

#### Scenario: Two teams see the same corpus type definition
- **WHEN** two different teams are each authorized to use the same registered corpus type
- **THEN** both observe identical `kind`/`mode`/`connector_kind` values for that type — neither team can define its own variant

### Requirement: A team may create a corpus instance only of a corpus type it is authorized to use
Creating a corpus instance SHALL fail closed unless the corpus type is registered and enabled in the deployment, and the requesting team is explicitly authorized to use that corpus type.

#### Scenario: Creation succeeds for an enabled, authorized type
- **GIVEN** a corpus type is registered and enabled in the deployment
- **AND** the requesting team is authorized to use that corpus type
- **WHEN** the team creates a corpus instance of that type
- **THEN** the corpus instance is created and scoped to that team

#### Scenario: Creation is refused for an unregistered or disabled type
- **GIVEN** a corpus type id that the deployment does not register, or has disabled
- **WHEN** any team attempts to create a corpus instance of that type
- **THEN** creation fails and no corpus instance is created

#### Scenario: Creation is refused for a team without authorization
- **GIVEN** a corpus type that is registered and enabled in the deployment
- **AND** the requesting team is not authorized to use that corpus type
- **WHEN** the team attempts to create a corpus instance of that type
- **THEN** creation fails and no corpus instance is created

### Requirement: Authorization to use a corpus type governs creation only, never content access
Authorization to use a corpus type SHALL determine only whether a team may create or operate an instance of that type. It SHALL NOT determine, expand, or restrict which documents any corpus instance's content is scoped to.

#### Scenario: Content scope is unaffected by type authorization
- **GIVEN** a team authorized to use a corpus type creates an instance scoped to its own team and tags
- **WHEN** that instance is queried for its content
- **THEN** the content returned reflects only the instance's own team/tag scope, unaffected by which teams are authorized to use the corpus type

### Requirement: A source connector reports a stable identity independent of its display path
Each item a source connector discovers SHALL carry an identity and a revision that are stable across repeated discovery calls, independent of the item's display path, so that a rename is representable without being treated as a deletion plus a new item.

#### Scenario: An unchanged item produces no reported change
- **WHEN** a source connector discovers changes twice in a row with nothing modified at the source in between
- **THEN** the second discovery reports no changes for that item

#### Scenario: A changed item is reported with its stable identity intact
- **WHEN** an item's content changes at the source between two discovery calls
- **THEN** the discovery reports a change for that item's same stable identity, with an updated revision

### Requirement: Deletion at the source is reported as a distinct, first-class change
A source connector SHALL report that an item was removed from the source as its own explicit kind of change, not left for the caller to infer by comparing listings.

#### Scenario: A removed item is reported as a deletion
- **WHEN** an item present in a prior discovery call is no longer present at the source
- **THEN** the next discovery call reports that item's removal explicitly

### Requirement: Pull-sourced documents are indistinguishable from pushed documents downstream
A document ingested through a pull-mode corpus instance SHALL be represented in FRED's document store the same way as a manually uploaded document, so that downstream systems (search, metadata, deletion) need no separate code path for its origin.

#### Scenario: A pulled document is retrievable like any other document
- **WHEN** a source connector's discovered change is ingested into a corpus instance
- **THEN** the resulting document is retrievable through the same document metadata access used for manually uploaded documents

### Requirement: A corpus instance never runs two overlapping synchronizations against its own state
For any single corpus instance, at most one synchronization SHALL be actively updating that instance's state at a time.

#### Scenario: A second synchronization does not start while one is in progress
- **GIVEN** a corpus instance's synchronization is currently in progress
- **WHEN** another synchronization for that same corpus instance is requested
- **THEN** the second synchronization does not run concurrently against the same instance state
