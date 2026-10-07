# team-resource-spaces Specification

## Purpose

Defines the current Team Resources surface and the boundary between corpus documents and technical agent files.

## Requirements

### Requirement: Team Resources exposes the corpus

The Team Resources page SHALL expose the searchable team corpus. It SHALL NOT expose general-purpose personal, team-shared, or agent-files roots.

#### Scenario: Open Team Resources

- **WHEN** a user opens Team Resources for a team
- **THEN** the corpus workspace is available without personal, team-shared, or agent-files tabs

### Requirement: Retired general-purpose areas are unavailable

The Knowledge Flow filesystem API SHALL reject the retired `/teams/{team_id}/users` and `/teams/{team_id}/shared` areas before accessing storage. Retirement SHALL NOT delete previously stored objects in those areas.

#### Scenario: Request a retired area

- **WHEN** a caller lists, reads, or mutates a path in either retired area
- **THEN** the request is rejected without reading or changing stored objects

### Requirement: Technical agent files remain available

Knowledge Flow SHALL retain authenticated binary upload, download, and delete operations for agent configuration assets and generated outputs under `/teams/{team_id}/agents/{agent_instance_id}/`. PPT Filler SHALL continue to load its per-instance template and publish downloadable presentations through these paths.

#### Scenario: Fill a presentation

- **GIVEN** an agent instance has a stored PPT Filler template
- **WHEN** the capability produces a presentation for a conversation
- **THEN** the template can be read and the generated presentation can be downloaded through the retained technical storage path

### Requirement: Corpus access remains separate

The corpus and conversation attachments SHALL continue to use their existing ingestion, metadata, search, and download APIs. The `/corpus` virtual filesystem view SHALL remain read-only, and `list_document_tree` SHALL continue to list authorized indexed documents.

#### Scenario: Agent lists corpus documents

- **WHEN** an authorized agent invokes `list_document_tree`
- **THEN** it receives the indexed documents permitted by the document-access contract
