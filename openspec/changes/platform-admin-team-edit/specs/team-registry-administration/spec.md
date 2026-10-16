## Purpose

Defines what platform-level administrators may do to a collaborative team's registry entry from the admin Teams page: create a team, and edit its name, description and team admins, under rules that keep every team named, described and administered.

## ADDED Requirements

### Requirement: Platform admins edit a team's registry entry

The control plane SHALL let a caller holding `organization#can_edit_team_registry` change an existing collaborative team's name, description and team admins in one request. `can_edit_team_registry` SHALL be held by `platform_admin` only. A caller without it SHALL receive 403 and nothing SHALL change. A personal space or an unknown team SHALL return 404.

#### Scenario: Platform admin edits a team

- **WHEN** a platform admin sends a new name, a new description, one admin to add and one admin to remove for an existing team
- **THEN** the response is 200 with the updated team, its name and description are the new values, and its admins roster reflects both changes

#### Scenario: Team manager cannot edit

- **WHEN** a caller holding `team_manager` but not `platform_admin` sends the same request
- **THEN** the response is 403 and the team is unchanged

#### Scenario: Personal space is not editable

- **WHEN** a platform admin targets a personal space
- **THEN** the response is 404

### Requirement: Registry edits keep the team's naming rules

A new name SHALL be trimmed, 1 to 180 characters, and unique among teams; a name already held by another team SHALL return 409, and renaming a team to its current name SHALL be a no-op. A new description SHALL follow the team description rules (20 to 500 characters once trimmed, `null` refused). Omitted fields SHALL stay unchanged.

#### Scenario: Name already taken

- **WHEN** a platform admin renames a team to the name of another team
- **THEN** the response is 409 and neither team changes

#### Scenario: Description too short

- **WHEN** a platform admin sends a description of 10 characters
- **THEN** the response is 422 and the stored description is unchanged

### Requirement: Registry edits keep at least one active team admin

The request SHALL name admins to add and admins to remove. An added user SHALL become `team_admin` when they have accepted the current team administrator charter, `pending_team_admin` otherwise. A removed admin SHALL lose `team_admin` and `pending_team_admin` and SHALL stay a team member. A request leaving the team with zero `team_admin` SHALL be refused with 409 and SHALL change nothing, including the name and description sent with it. A user listed in both lists SHALL be refused with 422.

#### Scenario: Removing the last active admin is refused

- **WHEN** a platform admin removes the team's only `team_admin` and adds a user who has not accepted the charter
- **THEN** the response is 409, the current admin keeps `team_admin`, and no pending nomination is written

#### Scenario: Removed admin stays a member

- **WHEN** a platform admin removes one of two team admins
- **THEN** the removed user no longer holds `team_admin` and still appears in the team's members as a member

### Requirement: Registry edits are audited

Every successful registry edit SHALL emit one audit event naming the actor, the team, the fields changed, and the user ids added and removed as admins. A refused edit SHALL emit none.

#### Scenario: Audit event on edit

- **WHEN** a platform admin renames a team and adds one admin
- **THEN** one audit event records the actor, the team id, the name change and the added user id

### Requirement: Admin Teams page creates and edits teams in one dialog

The admin Teams page SHALL show a "Create team" action in its header to every caller allowed to create teams. It SHALL open a dialog with the name, the description (required) and the team admins (at least one), and SHALL create the team on confirm. For a caller holding `can_edit_team_registry`, each team row SHALL offer an "Edit" action opening the same dialog prefilled with the team's name, description and admins; confirming SHALL send only what changed. The confirm action SHALL stay disabled while a required field is empty or invalid. Every label and message SHALL exist in French and English.

#### Scenario: Create from the header

- **WHEN** a team manager clicks "Create team", fills a name, a 30-character description and one admin, and confirms
- **THEN** the team is created, the dialog closes and the team appears in the table

#### Scenario: Edit from a row

- **WHEN** a platform admin clicks "Edit" on a team, changes its description and confirms
- **THEN** only the description is sent, the dialog closes and the table shows the new description

#### Scenario: No edit action for team managers

- **WHEN** a team manager without `platform_admin` opens the page
- **THEN** no row shows an "Edit" action

#### Scenario: Description limit reached

- **WHEN** an admin types a description up to 500 characters
- **THEN** the field's information line says "500 characters maximum" instead of stopping silently

### Requirement: Registry refusals are localized

A 409 refusing a team name already taken, the removal of the last active team admin, or a sole replacement still owing the charter SHALL carry a stable `code` (`team_name_taken`, `team_last_admin`, `team_admin_pending_charter`) next to its `detail`. The team dialog SHALL show its own French or English message for each code, and SHALL keep the generic error handling for any other failure.

#### Scenario: Last admin refusal in French

- **WHEN** a platform admin using the French interface removes a team's only active admin and saves
- **THEN** the response is 409 with `code` `team_last_admin`, and the toast shows the French message, not the server's English `detail`

### Requirement: Pending admins are distinguishable

The team listing SHALL expose `pending_admin_ids`, the admins listed who have not accepted the team administrator charter. The admin Teams page SHALL mark them: a "N pending" text after the row's avatars and a "Pending" line on their chip in the dialog.

#### Scenario: Nominee awaiting the charter

- **WHEN** a team has one active admin and one nominee who has not accepted the charter
- **THEN** its row shows "1 pending" next to the avatars and, in the edit dialog, only the nominee's chip reads "Pending"
