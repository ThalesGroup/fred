## Purpose

Makes every team administrator read and accept a deployment-defined charter of responsibilities before they hold administrator authority, records that acceptance, and keeps nominated administrators who have not accepted to a member's rights.

## ADDED Requirements

### Requirement: The charter is off unless a version is configured

The control-plane SHALL apply the charter only when `app.team_admin_charter_version` is set. When it is unset, nominating an administrator MUST grant `team_admin`, and recording an acceptance MUST be refused.

#### Scenario: Nomination with no version configured
- **WHEN** `app.team_admin_charter_version` is unset and a team admin grants `team_admin` to a member
- **THEN** the member holds `team_admin`

#### Scenario: Accepting with no version configured
- **WHEN** `app.team_admin_charter_version` is unset and a user records an acceptance
- **THEN** the request is refused with HTTP 409 and detail `team_admin_charter_disabled`, and nothing is stored

### Requirement: The charter text is a deployment-overridable markdown document

The frontend SHALL load the charter from `team-admin-charter.<lang>.md`, then `team-admin-charter.md`, with the same brand and theme archive override order as the terms of use. The stock document MUST be a generic template with no deployment-specific wording.

#### Scenario: Theme archive provides a French charter
- **WHEN** the theme archive contains `team-admin-charter.fr.md` and the browser language is French
- **THEN** the charter shown is the content of that file

#### Scenario: No override
- **WHEN** the theme archive contains no charter document
- **THEN** the stock template is shown

### Requirement: A nominated administrator is pending until they accept the configured version

While a version is configured, every grant of `team_admin` to a user who has not accepted that version SHALL write `pending_team_admin` instead. `pending_team_admin` MUST grant the rights of `team_member` and nothing more. It MUST NOT be requestable directly, and revoking it MUST require `can_administer_admins`. The last-admin guard and the rescue check MUST count `team_admin` only.

#### Scenario: Nominating an administrator who has not accepted
- **WHEN** a team admin grants `team_admin` to a member who has not accepted the current version
- **THEN** the member holds `pending_team_admin` and not `team_admin`

#### Scenario: Nominating an administrator who has accepted
- **WHEN** a team admin grants `team_admin` to a member who accepted the current version
- **THEN** the member holds `team_admin`

#### Scenario: A pending administrator has a member's rights
- **WHEN** a user holding only `pending_team_admin` updates the team's description
- **THEN** the request is refused as for any member, and the same user can still read the team's members

#### Scenario: Requesting the pending relation directly
- **WHEN** a client asks to grant `pending_team_admin`
- **THEN** the request fails validation with HTTP 422

#### Scenario: Cancelling a nomination
- **WHEN** a team admin revokes a member's `pending_team_admin`
- **THEN** the check uses `can_administer_admins`

### Requirement: Accepting records the acceptance and activates pending administrator roles

Recording an acceptance SHALL store the user's identifier, the configured charter version and the acceptance time, then turn every `pending_team_admin` the user holds into `team_admin`. One acceptance MUST cover every team. Recording the same version twice MUST keep the first acceptance time and MUST promote any pending relation left. Acceptances of earlier versions MUST be kept. The first acceptance of a version MUST emit a `team_admin.charter.accepted` audit event carrying the user identifier and the version.

#### Scenario: First acceptance
- **WHEN** a user pending on teams A and B accepts version `2026-09`
- **THEN** the acceptance is stored, the user holds `team_admin` on A and B and no `pending_team_admin`, and one audit event is emitted

#### Scenario: Repeated acceptance
- **WHEN** the same user accepts `2026-09` again
- **THEN** the request succeeds, the stored acceptance time is unchanged and no new audit event is emitted

### Requirement: A version change is reconciled at startup

At startup, when the configured version differs from the last version applied, the control-plane SHALL make every `team_admin` who has not accepted the configured version `pending_team_admin`, promote every `pending_team_admin` who has, and promote every `pending_team_admin` when the charter is off. When the version is unchanged it MUST change nothing. A failed reconciliation MUST stop the startup.

#### Scenario: Enabling the charter
- **WHEN** the charter was never enabled, a version is configured and a `team_admin` has not accepted it
- **THEN** after startup that user holds `pending_team_admin` on that team

#### Scenario: A new version already accepted
- **WHEN** the version changes and a pending administrator had already accepted the new version
- **THEN** after startup that user holds `team_admin`

#### Scenario: Turning the charter off
- **WHEN** the version is unset after being set
- **THEN** after startup every pending administrator holds `team_admin`

#### Scenario: Unchanged version
- **WHEN** the configured version equals the last one applied
- **THEN** startup changes no relation

### Requirement: A team's pages show the charter to its pending administrators

When a user opens a page of a team on which they hold `pending_team_admin`, the frontend SHALL show the charter in place of the page, with an Accept action that stays disabled until the end of the text has been reached. The home page, the personal space and the pages of teams where the user is not pending MUST NOT show it. After Accept, the team's pages MUST become available without reloading the app.

#### Scenario: Pending administrator opens their team
- **WHEN** a user holding `pending_team_admin` on a team opens one of its pages
- **THEN** the charter is shown with Accept disabled until the end of the text is reached

#### Scenario: Home page
- **WHEN** the same user is on the home page or in their personal space
- **THEN** no charter is shown

#### Scenario: Accept
- **WHEN** the user reaches the end of the charter and chooses Accept
- **THEN** the acceptance is recorded and the team's page is shown without a reload

### Requirement: Team settings show the charter to administrators and the pending state to everyone

Team settings SHALL show a read-only Responsibilities section with the charter to users who hold `team_admin` on that team, and to no one else. The member list MUST show a pending nomination on the administrator role.

#### Scenario: Administrator opens Responsibilities
- **WHEN** a `team_admin` opens the Responsibilities section
- **THEN** the charter is shown, with no Accept action

#### Scenario: Member opens Responsibilities
- **WHEN** a user who is only `team_member` navigates to the Responsibilities section URL
- **THEN** they are redirected to the Members section

#### Scenario: Member list
- **WHEN** a team admin opens the member list of a team with a pending administrator
- **THEN** that member's administrator chip reads "Admin (pending)"
