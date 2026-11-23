## ADDED Requirements

### Requirement: Home agents combine recent activity and accessible suggestions
The system SHALL return at most the requested number of distinct enabled, launchable instances the caller can use. Agents with current readiness-gating preparations that have not succeeded SHALL be excluded before the limit is applied. The optional request limit SHALL default to five and accept integers from 1 through 20; invalid limits SHALL be rejected. Recent conversation activity SHALL rank first, newest first. Remaining places SHALL come from accessible default-team and personal instances, ordered case-insensitively by name then instance id. OpenSearch SHALL NOT be required.

#### Scenario: Partial recent list
- **GIVEN** two usable recent instances and other accessible default or personal instances
- **WHEN** the caller opens home without OpenSearch
- **THEN** the two recent instances precede up to three distinct suggestions

#### Scenario: Caller selects a smaller limit
- **GIVEN** several usable recent and suggested instances
- **WHEN** the caller requests a limit of two
- **THEN** at most two instances are returned in the same ranking order

#### Scenario: Invalid limit
- **WHEN** the caller requests a limit below one or above 20
- **THEN** the request is rejected without querying agents

#### Scenario: Access and status filtering
- **WHEN** recent history references deleted, disabled, suspended, preparation-blocked or inaccessible instances
- **THEN** those instances are excluded before the requested limit is applied

#### Scenario: Personal-only and duplicate conversations
- **GIVEN** only personal agents and multiple conversations with one agent
- **WHEN** home agents are requested
- **THEN** each usable instance appears once, ranked by its latest known activity

### Requirement: Conversation activity is separate from metadata changes
Explicit conversation activity SHALL be recorded separately from general metadata changes using a server timestamp that cannot regress. Empty creation, title edits and context edits SHALL NOT establish activity. Unknown historical activity SHALL remain unknown; deleted conversations SHALL NOT contribute to home ranking.

#### Scenario: Rename and legacy records
- **WHEN** a legacy conversation is renamed without an activity update
- **THEN** its agent gains no recent priority

#### Scenario: Concurrent activity updates
- **WHEN** activity updates reach different replicas
- **THEN** shared stored activity does not move backwards

### Requirement: Home discovery exposes partial and total failures
History lookup failure SHALL allow suggestions with an explicit partial-failure indicator. Loading and failed discovery SHALL be distinguishable from a successful empty list.

#### Scenario: History query failure
- **WHEN** history lookup fails but agent suggestions can be read
- **THEN** suggestions are returned with history marked unavailable

#### Scenario: Discovery failure
- **WHEN** agent discovery fails
- **THEN** the UI offers an explicit error and retry
