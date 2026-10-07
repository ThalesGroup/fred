## Purpose

Defines the filesystem areas visible in Team Resources and available to agent authoring after the unused team-level personal area is retired.

## ADDED Requirements

### Requirement: Team Resources exposes supported roots
The Team Resources page SHALL expose the corpus root and, when resource spaces are enabled, the team-shared root for non-personal teams and the agent files root. It SHALL NOT expose a “Mon espace” root or issue personal-area filesystem requests.

#### Scenario: Resource spaces enabled for a team
- **WHEN** a user opens Team Resources for a non-personal team with resource spaces enabled
- **THEN** the available roots are the corpus, team-shared files, and agent files, without “Mon espace”

#### Scenario: Resource spaces disabled
- **WHEN** a user opens Team Resources with resource spaces disabled
- **THEN** only the corpus root is available

### Requirement: Team-level personal filesystem path is retired
The filesystem API SHALL NOT list or accept operations on `/teams/{team_id}/users` or its descendants. It SHALL continue to support `/teams/{team_id}/shared` and `/teams/{team_id}/agents/{agent_id}/users/{uid}` subject to their existing authorization rules. Retirement SHALL NOT delete previously stored personal-area objects.

#### Scenario: Personal path request
- **WHEN** an authorized team member requests listing, metadata, content, search, or mutation under `/teams/{team_id}/users`
- **THEN** the filesystem API rejects the unsupported area without reading or changing its stored objects

#### Scenario: Agent-owned files remain accessible
- **WHEN** an authorized user accesses `/teams/{team_id}/agents/{agent_id}/users/{uid}` for their own uid
- **THEN** the existing agent file operations remain available

### Requirement: Template lookup uses supported areas
Agent authoring SHALL resolve a named workspace template from the agent's own `templates/` directory first and the team-shared `templates/` directory second. It SHALL NOT use the retired team-level personal area as a fallback.

#### Scenario: Agent template overrides shared template
- **WHEN** the same named template exists in the agent's own files and team-shared files
- **THEN** template lookup returns the agent's own file

#### Scenario: Only shared template exists
- **WHEN** the named template is absent from the agent's own files and present in team-shared files
- **THEN** template lookup returns the shared file
