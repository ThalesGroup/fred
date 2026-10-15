## MODIFIED Requirements

### Requirement: Platform administrators manage live exceptions

Only people holding the existing platform-management permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using the configured user directory for identity lookup and Fred for admission state, team authorization and Free-team controls, filtering state, effective admission sources displayed by type and team name without team UIDs, own-session claim selection, rule editing and draft preview. In `user_directory: keycloak`, both federated identities known to Keycloak and identities created directly there SHALL be selectable before their first Fred request; in `user_directory: local`, identities SHALL come from Fred's `users` table. Team administrators and team managers SHALL NOT obtain this authority through their existing roles. Removing an individual exception SHALL NOT remove an identity or revoke independent team sources. Rule updates SHALL be explicit, atomic and versioned; stale concurrent saves SHALL return a conflict without overwriting another administrator's changes. Preview SHALL NOT change filtering, policy, T0, membership or evidence selected only by the proposed rule.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** an administrator adds an existing identity from the configured directory or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Administrator authorizes a selected user list

- **WHEN** a platform administrator selects any nonempty list of existing directory identities and grants admission
- **THEN** the operation SHALL atomically add removable manual exceptions without overwriting existing sources
- **WHEN** the list includes an unknown identity or is submitted by a non-platform administrator
- **THEN** no exceptions SHALL be granted

#### Scenario: Keycloak identity has not visited Fred

- **GIVEN** `user_directory: keycloak` and a human identity created directly in Keycloak or made known there by federation
- **WHEN** the identity has no Fred profile row and an administrator searches and selects it
- **THEN** the directory profile SHALL be displayed and the administrator SHALL be able to grant it an individual exception

#### Scenario: Local directory remains selectable

- **GIVEN** `user_directory: local`
- **WHEN** an administrator searches, lists, or grants an individual exception
- **THEN** Fred's local identities SHALL supply the profile and unknown local identities SHALL be rejected

#### Scenario: Directory profile changes or disappears

- **WHEN** a directory profile changes after an exception was granted
- **THEN** a later whitelist read SHALL show the current directory profile for the same identity id without changing the exception
- **WHEN** an existing exception's identity cannot be resolved
- **THEN** the entry SHALL remain visible with its identity id and origin, and SHALL remain removable

#### Scenario: Directory lookup fails

- **WHEN** the configured directory is unavailable during a search, grant validation, or initial-import preparation
- **THEN** the operation SHALL report an availability error and SHALL NOT treat an empty fallback as authoritative or partially grant exceptions

#### Scenario: Leaving an allowed or Free team revokes its global source

- **WHEN** a person leaves or is removed from an allowed or Free team
- **THEN** the next direct, cached-token or delegated request on any participating reader SHALL no longer use that team for platform admission
- **AND** the person SHALL be refused when no independent source remains, while other grants and ordinary membership of other teams remain unchanged

#### Scenario: Unauthorized administrative call

- **WHEN** an ordinary person, team administrator or team manager requests claim discovery, preview, policy updates or exception administration
- **THEN** the call SHALL be refused and admission state SHALL remain unchanged

#### Scenario: Administrator sees provenance

- **WHEN** an administrator lists allowed users
- **THEN** individual entries SHALL identify manual or T0 origin and derived entries SHALL identify each authorized or Free team

#### Scenario: Preview explains an unsaved rule

- **WHEN** an administrator tests a draft against their verified token
- **THEN** the UI SHALL show per-condition results, missing or incompatible claim explanations, the aggregate rule result and whether they would be admitted with filtering active including independent sources, without saving the draft

#### Scenario: Two administrators save concurrently

- **WHEN** a save uses an older revision than the active policy
- **THEN** the system SHALL return HTTP 409 and retain the newer policy, while the UI preserves the unsaved draft and explains the conflict

User rows SHALL show identifier, first name and last name using the team-member table presentation. The whitelist SHALL list individual exceptions only, and its search and add dialog SHALL use the configured directory's current profiles. Searches and pages SHALL not show stale results from a previous request. Large selections SHALL use bounded work and grants SHALL remain atomic.

#### Scenario: Grant more than 100 people

- **WHEN** an administrator submits more than 100 known identities
- **THEN** all missing exceptions SHALL be added atomically, duplicate identities ignored and existing origins preserved
- **WHEN** an identity in a later batch is unknown
- **THEN** the complete operation SHALL roll back

### Requirement: T0 grandfathering is an explicit fixed snapshot

The system SHALL provide an administrator-triggered preview and one atomic import of existing human identities in the configured directory before filtering activation. Keycloak mode SHALL include identities known to Keycloak through federation or direct creation; local mode SHALL use Fred's `users` table. Known current matches from Fred's verified claim observations SHALL not require individual entries; unknown classifications SHALL be included conservatively without inferring token claims from directory profile fields. T0 entries SHALL be individually removable. Import completion SHALL fix the population; later registrations SHALL not be grandfathered by a retry, restart or upgrade. Activation's population review SHALL use the same configured directory population rather than an unrelated local-user subset.

#### Scenario: Existing user without a stored attribute

- **WHEN** an administrator imports T0 and an existing human in the configured directory has no reliable verified-claim classification
- **THEN** that identity SHALL receive a removable T0 exception

#### Scenario: Keycloak population differs from Fred profiles

- **GIVEN** `user_directory: keycloak` and Keycloak contains a human identity absent from Fred's `users` table
- **WHEN** an administrator previews and commits the initial import
- **THEN** the preview SHALL count that identity and the import SHALL create its T0 exception if the rule cannot reliably accept it
- **AND** a Fred-only row without a current Keycloak human identity SHALL NOT be newly imported

#### Scenario: Removed entry and later registration stay excluded

- **WHEN** T0 has completed, one imported exception is removed, and another person registers afterward
- **THEN** neither a repeated import request nor restart SHALL restore the removed entry or admit the later registration

#### Scenario: Concurrent imports

- **WHEN** two administrators attempt T0 import concurrently
- **THEN** only one fixed snapshot SHALL commit and the other request SHALL report the completed state
