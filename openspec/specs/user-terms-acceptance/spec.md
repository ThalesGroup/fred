# user-terms-acceptance Specification

## Purpose

Define configurable Terms of Use versions, durable user acceptance and the admission behavior when deployments require updated terms.

## Requirements

### Requirement: Accept the configured version

The system SHALL accept and persist the configured GCU version as an opaque string in the existing user record, with its acceptance timestamp. Each acceptance SHALL replace the previously stored version and timestamp. User details SHALL expose the stored version or null, without a fixed version enumeration or GCU acceptance history.

#### Scenario: Reaccept a newer version
- **GIVEN** a user has accepted `v1` and the active configured version is `v2`
- **WHEN** the user accepts the current terms
- **THEN** the acceptance request succeeds and user details report `v2` with the new acceptance timestamp

#### Scenario: Deployment-owned version identifier
- **GIVEN** the active configured version is `2026-10`
- **WHEN** a user accepts the terms
- **THEN** the persisted and returned version is exactly `2026-10`

### Requirement: Match the active version for admission

When GCU enforcement is enabled, protected human requests SHALL require the currently stored accepted version exactly matching the active configured version. Existing service and asserted-user exemptions SHALL remain unchanged. Unset GCU configuration or disabled security SHALL preserve existing bypass behavior.

#### Scenario: Old acceptance blocks protected access
- **GIVEN** a user has accepted `v1` and the active version changes to `v2`
- **WHEN** the user makes a protected human request before reaccepting
- **THEN** admission fails with HTTP 403 and `user_not_accept_gcu`

#### Scenario: New acceptance restores access
- **GIVEN** a user successfully accepts the active version `v2`
- **WHEN** the user makes a protected human request
- **THEN** GCU admission succeeds

#### Scenario: Version identifiers are case sensitive
- **GIVEN** the accepted version is `v1` and the active version is `V1`
- **WHEN** the user makes a protected human request
- **THEN** GCU admission requires acceptance of `V1`

#### Scenario: Existing exemptions remain usable
- **WHEN** a request qualifies for an existing service or asserted-user GCU exemption, or GCU enforcement is disabled
- **THEN** the GCU check does not introduce a new acceptance requirement

#### Scenario: Return to an overwritten version
- **GIVEN** a user accepted `v1` and then `v2`, replacing the stored acceptance
- **WHEN** the active version returns to `v1`
- **THEN** protected admission fails until `v1` is accepted again and user details still report `v2`

#### Scenario: Repeated acceptance replaces the timestamp
- **GIVEN** a user already accepted the configured version
- **WHEN** the user accepts that version again
- **THEN** the stored version remains the same and its timestamp records the latest acceptance

### Requirement: Preserve existing acceptance during upgrade

Upgrading version storage SHALL preserve legacy `v1` acceptance, null acceptance, timestamps, user identity and resource-storage counters. A rollback that cannot represent a stored accepted version SHALL fail without altering data.

#### Scenario: Upgrade legacy records
- **GIVEN** the legacy database contains accepted `V1` entries and users without acceptance
- **WHEN** the version-storage migration runs
- **THEN** legacy entries represent accepted `v1`, unaccepted users remain unaccepted and all other user data is preserved

#### Scenario: Safe legacy rollback
- **GIVEN** all accepted versions are `v1` or null
- **WHEN** the version-storage migration is downgraded
- **THEN** the legacy representation is restored with acceptance timestamps and other user data preserved

#### Scenario: Refuse lossy rollback
- **GIVEN** the current stored acceptance is `v2` or another version outside the legacy schema
- **WHEN** a downgrade is attempted
- **THEN** it fails before schema or acceptance data is changed

### Requirement: Enroll default teams only on first acceptance

GCU reacceptance SHALL NOT repeat first-acceptance enrollment into default teams. First acceptance SHALL preserve the existing default-team policy and SHALL NOT be recorded if required enrollment fails.

#### Scenario: Reacceptance preserves team membership choices
- **GIVEN** a user accepted `v1` and subsequently left a default team
- **WHEN** the user accepts `v2`
- **THEN** the acceptance is recorded and the user is not re-enrolled into that team

#### Scenario: First acceptance still enrolls eligible users
- **GIVEN** a user has no prior GCU acceptance
- **WHEN** the user accepts the active version
- **THEN** eligible default-team enrollment completes before acceptance is recorded

#### Scenario: Enrollment failure does not record acceptance
- **GIVEN** a user has no prior GCU acceptance
- **WHEN** required default-team enrollment fails during acceptance
- **THEN** no successful acceptance is recorded
