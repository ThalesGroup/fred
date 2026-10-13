## ADDED Requirements

### Requirement: Team invitations use the join route

The frontend SHALL generate and recover Free-team invitation URLs at `/join/:token`, respecting its configured basename. An authenticated person, including one denied normal platform admission, SHALL reach the standalone enrollment page at that route. The previous `/join-free/:token` route SHALL not be served. Fred access logs SHALL redact the opaque token from the new route.

#### Scenario: Create and open an invitation

- **WHEN** a platform administrator creates or recovers a Free-team invitation
- **THEN** the displayed and copied URL SHALL use `/join/:token`
- **AND** opening that URL SHALL render the standalone enrollment page through the authentication redirect when needed

#### Scenario: Protect the new capability path

- **WHEN** admission denies normal platform access while a person opens `/join/:token`
- **THEN** the person SHALL remain on the enrollment route
- **AND** Fred access logs SHALL not expose the token

#### Scenario: Retired route

- **WHEN** a person requests `/join-free/:token`
- **THEN** the frontend SHALL not route that path to the enrollment page
