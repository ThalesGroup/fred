# Team Member Roles Specification

## Purpose

Defines how administrators change cumulative team roles while preserving membership and protecting the team's administrator coverage.

## Requirements

### Requirement: Revoking the last elevated role retains membership

When an authorized actor revokes a member's only stored elevated team role, the control-plane SHALL retain that person on the team with a direct `team_member` relation. This SHALL apply to `team_admin`, `pending_team_admin`, `team_editor`, and `team_analyst`. The member-management role toggle SHALL reflect the resulting simple-member state.

#### Scenario: Active administrator becomes a simple member

- **WHEN** an authorized team administrator turns off Alice's `team_admin` role, Alice holds no other stored team role, and another active administrator remains
- **THEN** the request succeeds, Alice holds `team_member` but not `team_admin`, and she remains in the team members list

#### Scenario: Pending administrator nomination is cancelled

- **WHEN** an authorized team administrator turns off Alice's `pending_team_admin` nomination and Alice holds no other stored team role
- **THEN** Alice remains in the team as `team_member` without an administrator nomination

#### Scenario: Editor or analyst becomes a simple member

- **WHEN** an authorized team administrator revokes a person's sole `team_editor` or sole `team_analyst` role
- **THEN** the person remains in the team with `team_member` and without the revoked elevated role

#### Scenario: Other stored roles remain unchanged

- **WHEN** an authorized team administrator revokes one elevated role from a person who already holds another stored team role
- **THEN** only the requested role is removed and the other stored roles remain

### Requirement: Role revocation preserves authorization and explicit removal

The control-plane MUST enforce the existing permission for the role being revoked and, when it creates a direct `team_member` relation, the permission to administer members. Only an active `team_admin` MAY revoke a `pending_team_admin` nomination. It MUST prevent removal of the team's last active `team_admin`, even when pending nominations exist. A concurrent role revocation MUST NOT restore membership after explicit member removal. It MUST NOT remove a person from the team through role revocation. Removing the person entirely SHALL remain an explicit member-removal action. Revoking a sole direct `team_member` relation MUST remain refused.

#### Scenario: Last active administrator is protected

- **WHEN** a request would revoke the team's last active `team_admin`
- **THEN** the request fails and the target's stored relations remain unchanged

#### Scenario: Pending nominee does not satisfy last-admin guard

- **WHEN** the only active `team_admin` is revoked while another person holds `pending_team_admin`
- **THEN** the request fails and both stored relations remain unchanged

#### Scenario: Pending nomination requires an active administrator

- **WHEN** a caller with only `pending_team_admin` attempts to cancel another pending nomination and no active `team_admin` exists
- **THEN** the request fails and the nominee's stored relations remain unchanged

#### Scenario: Unauthorized revocation is refused

- **WHEN** a caller lacks permission to administer the requested role
- **THEN** the request fails and the target's stored relations remain unchanged

#### Scenario: Sole simple-member role cannot be revoked

- **WHEN** a caller revokes the only stored `team_member` relation
- **THEN** the request fails and the person remains on the team until an explicit member-removal action succeeds

#### Scenario: Concurrent explicit removal wins over role revocation

- **WHEN** a role revocation and an explicit removal target the same person concurrently
- **THEN** their relation writes are serialized and a completed removal leaves the person without team membership

#### Scenario: Explicit member removal remains separate

- **WHEN** an authorized actor removes a member using the member-removal action
- **THEN** the person's stored team roles are removed and the existing membership-removal lifecycle applies
