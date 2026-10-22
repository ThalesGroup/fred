## MODIFIED Requirements

### Requirement: Platform admins edit a team's registry entry

The control plane SHALL let a caller holding `organization#can_edit_team_info` change an existing collaborative team's name and description. This permission SHALL be held by `team_manager` and `platform_admin`. Changing team admins in the same request SHALL additionally require `organization#can_edit_team_registry`, held by `platform_admin` only. A team manager's request to add or remove an admin SHALL receive 403 and SHALL change neither registry fields nor admin relations. A personal space or an unknown team SHALL return 404.

#### Scenario: Platform admin edits a team

- **WHEN** a platform admin sends a new name, a new description, one admin to add and one admin to remove for an existing team
- **THEN** the response is 200 with the updated team, its name and description are the new values, and its admins roster reflects both changes

#### Scenario: Team manager cannot edit

- **WHEN** a caller holding `team_manager` but not `platform_admin` asks to change an existing team's admin roster
- **THEN** the response is 403 and the roster is unchanged

#### Scenario: Team manager edits team details

- **WHEN** a caller holding `team_manager` but not `platform_admin` changes the name and description of an existing collaborative team
- **THEN** the response is 200 and the team details change without changing its admins

#### Scenario: Team manager cannot appoint an admin

- **WHEN** a caller holding only `team_manager` sends a name change and asks to add or remove an admin in the same request
- **THEN** the response is 403 and neither the name nor any admin relation changes

#### Scenario: Personal space is not editable

- **WHEN** a platform admin targets a personal space
- **THEN** the response is 404

### Requirement: Admin Teams page creates and edits teams in one dialog

The admin Teams page SHALL show a "Create team" action in its header to every caller allowed to create teams. It SHALL open a dialog with the name, the description (required) and the initial team admins (at least one), and SHALL create the team on confirm. For a caller holding `can_edit_team_info`, each team row SHALL offer an "Edit" action opening the same dialog prefilled with the team's name and description; callers also holding `can_edit_team_registry` SHALL be able to edit the admins there, while team managers SHALL not see or submit admin edits. Confirming SHALL send only what changed. The confirm action SHALL stay disabled while a required field is empty or invalid. Escape SHALL NOT close the dialog, so a draft is not lost by accident. The admin search in the creation or admin-edit form SHALL open from two characters with localized searching and no-match messages, above the dialog rather than clipped by it. Every label and message SHALL exist in French and English.

#### Scenario: Create from the header

- **WHEN** a team manager clicks "Create team", fills a name, a 30-character description and one admin, and confirms
- **THEN** the team is created, the dialog closes and the team appears in the table

#### Scenario: Edit from a row

- **WHEN** a platform admin clicks "Edit" on a team, changes its description and confirms
- **THEN** only the description is sent, the dialog closes and the table shows the new description

#### Scenario: No edit action for team managers

- **WHEN** a team manager without `platform_admin` opens the page
- **THEN** no row SHALL offer an action to edit its admins

#### Scenario: Team manager sees a bounded edit action

- **WHEN** a team manager without `platform_admin` opens the page
- **THEN** each collaborative team row SHALL offer an "Edit" action for name and description without admin nomination controls

#### Scenario: Description limit reached

- **WHEN** an admin types a description up to 500 characters
- **THEN** the field's information line says "500 characters maximum" instead of stopping silently
