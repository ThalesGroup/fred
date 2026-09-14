## Purpose

Makes every team administrator read and accept a deployment-defined charter of responsibilities, records that acceptance, and keeps administrator-only team permissions inactive until it is given.

## ADDED Requirements

### Requirement: The charter is off unless a version is configured

The control-plane SHALL apply the charter only when `app.team_admin_charter_version` is set. When it is unset, team permissions MUST behave as if the charter did not exist, no user MUST be prompted, and recording an acceptance MUST be refused.

#### Scenario: No version configured
- **WHEN** `app.team_admin_charter_version` is unset and a `team_admin` who never accepted anything updates their team
- **THEN** the update succeeds and the team permissions returned to them include `can_update_info`

#### Scenario: Status with no version configured
- **WHEN** `app.team_admin_charter_version` is unset and any user reads their charter status
- **THEN** the response reports that no acceptance is required

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

### Requirement: Acceptance is recorded per user and charter version

Recording an acceptance SHALL store the user's identifier, the configured charter version and the acceptance time. One acceptance MUST cover every team the user administers. Recording the same version twice MUST keep the first acceptance time. Acceptances of earlier versions MUST be kept. Each new acceptance MUST emit a `team_admin.charter.accepted` audit event carrying the user identifier and the version.

#### Scenario: First acceptance
- **WHEN** a user records an acceptance while version `2026-09` is configured
- **THEN** an acceptance for that user and `2026-09` is stored with the current time and a `team_admin.charter.accepted` audit event is emitted

#### Scenario: Repeated acceptance
- **WHEN** a user who already accepted `2026-09` records an acceptance again
- **THEN** the request succeeds and the stored acceptance time is unchanged

#### Scenario: Acceptance covers all administered teams
- **WHEN** a user who is `team_admin` of teams A and B accepts the current version once
- **THEN** administrator-only permissions are active on both A and B

### Requirement: The charter status tells the caller whether they must accept

The control-plane SHALL let any authenticated user read their charter status, reporting whether an acceptance is required and, when the current version was accepted, when. An acceptance MUST be required exactly when a version is configured, the user holds `team_admin` on at least one team, and the user has not accepted that version.

#### Scenario: Administrator who has not accepted
- **WHEN** a `team_admin` of one team who has not accepted the current version reads their status
- **THEN** the response reports that an acceptance is required

#### Scenario: User who administers no team
- **WHEN** a user who holds no `team_admin` relation reads their status
- **THEN** the response reports that no acceptance is required

#### Scenario: Administrator who has accepted
- **WHEN** a `team_admin` who accepted the current version reads their status
- **THEN** the response reports that no acceptance is required and includes the acceptance time

### Requirement: Administrator-only team permissions require acceptance of the current version

While a version is configured, a user who has not accepted it SHALL be denied `can_update_info`, `can_administer_members`, `can_administer_editors`, `can_administer_analysts` and `can_administer_admins` on every team, even when they hold `team_admin`. A denied request MUST fail with HTTP 403 and detail `team_admin_charter_not_accepted`, and those permissions MUST be absent from the team permissions returned to the user. Every other team permission MUST be unaffected, including permissions `team_admin` shares with another role. Granting, revoking and counting the `team_admin` relation MUST be unaffected.

#### Scenario: Administrator who has not accepted updates the team
- **WHEN** a `team_admin` who has not accepted the current version updates the team's description
- **THEN** the request fails with HTTP 403 and detail `team_admin_charter_not_accepted`

#### Scenario: Administrator who has not accepted adds a member
- **WHEN** a `team_admin` who has not accepted the current version adds a member to the team
- **THEN** the request fails with HTTP 403 and detail `team_admin_charter_not_accepted` and no relation is written

#### Scenario: Permissions returned before acceptance
- **WHEN** a `team_admin` who has not accepted the current version reads the team
- **THEN** the returned permissions contain none of the five administrator-only permissions and still contain `can_read_members`

#### Scenario: Administrator accepts
- **WHEN** a `team_admin` accepts the current version and then updates the team's description
- **THEN** the update succeeds

#### Scenario: Version changes
- **WHEN** a `team_admin` accepted `2026-09` and the configured version becomes `2027-01`
- **THEN** administrator-only requests fail with HTTP 403 and detail `team_admin_charter_not_accepted` until they accept `2027-01`

#### Scenario: Shared analyst permission
- **WHEN** a user holding both `team_admin` and `team_analyst` has not accepted the current version
- **THEN** the returned permissions still contain `can_run_evaluations`

#### Scenario: Other roles are unaffected
- **WHEN** a `team_editor` who has never accepted the charter uploads a team resource
- **THEN** the request is authorized as it would be without the charter

#### Scenario: Nominating an administrator
- **WHEN** a `team_admin` who accepted the current version grants `team_admin` to a member who has not
- **THEN** the relation is written and the new administrator's administrator-only permissions stay inactive until they accept

### Requirement: Team administrators are prompted to accept on their team's pages

When a user whose charter status requires an acceptance opens a page of a team on which they hold `team_admin`, the frontend SHALL show a pop-up with the charter and two actions, Accept and Later. The pop-up MUST NOT appear on the home page, on the personal space, or on the pages of a team the user does not administer. Accept MUST stay disabled until the end of the charter text has been reached. Later MUST close the pop-up without recording anything, and the pop-up MUST NOT appear again until the next app load. After Accept, administrator actions MUST become available without reloading the app.

#### Scenario: Pending acceptance on a team page
- **WHEN** a `team_admin` whose status requires an acceptance opens a page of the team they administer
- **THEN** the pop-up shows the charter with Accept disabled until the end of the text is reached

#### Scenario: Home page
- **WHEN** the same user is on the home page
- **THEN** no pop-up is shown

#### Scenario: Team the user does not administer
- **WHEN** the same user opens a page of a team where they only hold `team_member`
- **THEN** no pop-up is shown

#### Scenario: Later
- **WHEN** the user chooses Later
- **THEN** the pop-up closes, no acceptance is recorded, and it does not appear again on team pages until the app is loaded again

#### Scenario: Accept
- **WHEN** the user reaches the end of the charter and chooses Accept
- **THEN** the acceptance is recorded, the pop-up closes and the team settings show administrator actions without a reload

#### Scenario: Nothing pending
- **WHEN** a `team_admin` whose status requires no acceptance opens a page of their team
- **THEN** no pop-up is shown

### Requirement: Team settings give team administrators access to the charter

Team settings SHALL show a Responsibilities section to users who hold `team_admin` on that team, and to no one else. The section MUST show the charter, the acceptance time when the current version is accepted, and an Accept action when it is not. While an acceptance is pending, team settings MUST explain that administrator rights are inactive until the charter is accepted.

#### Scenario: Administrator opens Responsibilities
- **WHEN** a `team_admin` who accepted the current version opens the Responsibilities section
- **THEN** the charter and the acceptance time are shown, with no Accept action

#### Scenario: Pending administrator opens team settings
- **WHEN** a `team_admin` whose acceptance is pending opens team settings
- **THEN** a notice explains that administrator rights are inactive until the charter is accepted and leads to the Responsibilities section

#### Scenario: Member opens Responsibilities
- **WHEN** a user who is only `team_member` navigates to the Responsibilities section URL
- **THEN** they are redirected to the Members section
