## MODIFIED Requirements

### Requirement: T0 grandfathering is an explicit fixed snapshot

The system SHALL provide an administrator-triggered preview and an atomic initial import of existing human identities in the configured directory before filtering activation. Keycloak mode SHALL include identities known to Keycloak through federation or direct creation; local mode SHALL use Fred's `users` table. Known current matches from Fred's verified claim observations SHALL not require individual entries; unknown classifications SHALL be included conservatively without inferring token claims from directory profile fields. T0 entries SHALL be individually removable. Import completion SHALL fix the population until an administrator explicitly refreshes it; later registrations SHALL not be grandfathered by an ordinary initial-import retry, restart or upgrade. Activation's population review SHALL use the same configured directory population rather than an unrelated local-user subset.

Regardless of filtering state, an administrator SHALL be able to refresh a completed import without changing the filtering switch. When reliable removal history is available, every refresh dialog SHALL offer a choice between preserving recorded individual removals and including previously removed people. Preservation SHALL be the initial selection on each opening in that case. The selected mode SHALL determine the preview and submitted operation. Including removed people SHALL require a confirmation warning that those people can regain access. Preview, changing the selection and cancelling SHALL NOT modify admission state. Refresh SHALL add missing T0 exceptions according to the saved rule and selected mode, preserving every existing individual grant's source, actor and date, and SHALL NOT delete existing grants. Successful refresh SHALL expose its completion time and actual number of additions.

Individual exception removals SHALL be recorded durably and atomically with revocation, including removals of manually granted exceptions. Preservation mode SHALL exclude recorded removals that no longer have an individual grant; inclusion mode SHALL permit their re-addition when they remain candidates. For a deployment with a completed pre-upgrade import and no reliable removal history, the next explicit refresh SHALL require inclusion mode. Both the UI and server SHALL prevent preservation mode until that full refresh succeeds. The UI SHALL warn that removal history is unavailable, the whole T0 population will be recalculated and previously removed candidates can regain access, and SHALL require explicit confirmation. A successful full refresh SHALL establish a new baseline and enable both modes on subsequent refreshes. An upgrade or page opening SHALL NOT execute this import automatically. A fresh deployment SHALL NOT display the missing-history warning.

Only platform administrators SHALL preview or execute refresh. Refresh SHALL fail without partial writes when the directory is unavailable, or the policy or completed import used for confirmation is stale. Concurrent refreshes based on the same completion SHALL NOT both commit. Every committed refresh SHALL emit one bounded security audit summary containing the actor, selected mode and actual additions, without claim values or one event per identity. Failed, cancelled and stale operations SHALL NOT emit a success event.

#### Scenario: Existing user without a stored attribute

- **WHEN** an administrator imports T0 and an existing human in the configured directory has no reliable verified-claim classification
- **THEN** that identity SHALL receive a removable T0 exception

#### Scenario: Keycloak population differs from Fred profiles

- **GIVEN** `user_directory: keycloak` and Keycloak contains a human identity absent from Fred's `users` table
- **WHEN** an administrator previews and commits the initial import or an explicit refresh
- **THEN** the preview SHALL count that identity and the import SHALL create its T0 exception if the rule cannot reliably accept it and the selected mode permits it
- **AND** a Fred-only row without a current Keycloak human identity SHALL NOT be newly imported

#### Scenario: Removed entry and later registration stay excluded

- **WHEN** T0 has completed, one imported exception is removed, and another person registers afterward
- **THEN** an ordinary initial-import retry or restart SHALL neither restore the removed entry nor import the later registration
- **AND** the completed status SHALL remain readable without scanning the directory again

#### Scenario: Concurrent imports

- **WHEN** two administrators attempt the initial T0 import concurrently
- **THEN** only one initial snapshot SHALL commit and the other request SHALL report the completed state

#### Scenario: Choose the refresh mode each time

- **WHEN** an administrator opens the refresh dialog after T0 completion with filtering on or off
- **THEN** both modes SHALL be offered with preservation selected, a preview for that mode and an explicit confirmation action
- **WHEN** the administrator selects inclusion mode
- **THEN** the preview SHALL reflect that mode and a warning SHALL explain that previously removed people can regain access
- **WHEN** the dialog is cancelled and reopened
- **THEN** no mutation SHALL have occurred and preservation SHALL be selected again

#### Scenario: Preserve manual removals

- **GIVEN** T0 has completed, individual exceptions of either origin have subsequently been removed and a new directory identity exists
- **WHEN** an administrator refreshes in preservation mode
- **THEN** recorded removed identities SHALL remain without an individual grant, the new candidate SHALL receive a T0 exception and existing grants SHALL retain their provenance
- **AND** those removals SHALL remain effective after restart or execution on another replica

#### Scenario: Include previously removed people

- **GIVEN** T0 has completed and a removed identity still exists in the configured directory and cannot be accepted by the saved rule
- **WHEN** an administrator confirms refresh in inclusion mode after reading its warning
- **THEN** that identity SHALL receive a new T0 exception
- **AND** existing grants, team sources and the filtering switch SHALL remain unchanged

#### Scenario: Legacy test environment has no reliable removal history

- **GIVEN** a deployment completed T0 before removal tracking was introduced
- **WHEN** an administrator opens refresh
- **THEN** inclusion mode SHALL be required and a warning SHALL explain the missing history, full recalculation and potential return of manually removed people
- **AND** no import SHALL run before explicit confirmation, while a preservation request SHALL be rejected by the server
- **WHEN** the full refresh succeeds
- **THEN** the new baseline SHALL be recorded and both modes SHALL be available on the next refresh
- **WHEN** that import is cancelled or fails
- **THEN** the reset SHALL remain required and the warning SHALL remain visible on the next attempt

#### Scenario: Filtering is active or becomes active during refresh

- **WHEN** a refresh is requested while filtering is active, including when activation commits during refresh preparation
- **THEN** refresh SHALL succeed when the remaining confirmation preconditions are current, adding only eligible exceptions and leaving filtering active
- **AND** identities without a new exception SHALL remain subject to the active admission rules

#### Scenario: Concurrent refresh or policy update

- **WHEN** two refreshes use the same completed import, or the saved policy changes after the confirmation preview
- **THEN** a stale request SHALL return a conflict without overwriting or extending the newer state
- **AND** replaying a committed refresh request SHALL NOT re-add a subsequently removed exception

#### Scenario: Unavailable directory or unauthorized caller

- **WHEN** the configured directory fails or a caller without platform-management permission attempts refresh
- **THEN** no exceptions, removal records or completion state SHALL be changed and no successful refresh audit SHALL be emitted
