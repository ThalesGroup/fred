## Purpose

Defines the Simple agent form's capability packs, their relationship to the stored capability selection, and how members change that selection while retaining Advanced controls.

## ADDED Requirements

### Requirement: One pack grants team resources and conversation attachments

The Simple capabilities view SHALL offer one "Team resources" pack for team corpus access and conversation attachments. It SHALL NOT offer a standalone "Conversation attachments" pack. When enabled, the combined pack SHALL select each available capability it grants and SHALL configure document access to search the corpus and allow conversation attachments.

#### Scenario: Enable the combined pack for a new agent

- **WHEN** a member enables "Team resources" for a new agent whose team can use document access
- **THEN** the agent can use team corpus resources and attach files in conversation, with attachments-only search disabled

#### Scenario: Only one resource pack is shown

- **WHEN** a member opens the Simple capabilities view
- **THEN** "Team resources" appears as the single resource pack and no "Conversation attachments" card appears

#### Scenario: Admin availability limits the pack

- **WHEN** a team can use document access but an included reading or tabular capability is unavailable
- **THEN** enabling "Team resources" enables only the available capabilities and marks the unavailable capability in its included list

#### Scenario: Document access is unavailable

- **WHEN** the team cannot use document access
- **THEN** the combined resource pack is not selectable

### Requirement: The combined pack respects existing selections and Advanced overrides

An agent's stored capability selection SHALL remain unchanged on deployment and on unrelated form edits. The form SHALL apply the combined resource defaults to a new agent whose template preselects document access, or when a member enables the resource pack in Simple. A member's explicit change to document access in Advanced SHALL persist across later edits until changed again. The pack's displayed on/off state SHALL derive from document access selection rather than a particular document access option.

#### Scenario: Existing corpus-only agent is not changed by deployment

- **WHEN** the new frontend is deployed and no member edits an existing corpus-only agent
- **THEN** the agent retains its stored configuration without conversation attachments

#### Scenario: Existing corpus-only agent is edited without changing the pack

- **WHEN** a member opens and saves an existing corpus-only agent without changing its resource pack or document access settings
- **THEN** conversation attachments remain disabled

#### Scenario: Existing attachment-only agent adopts the combined pack

- **WHEN** a member re-enables the resource pack in Simple and saves an existing attachment-only agent
- **THEN** corpus access becomes enabled alongside conversation attachments, subject to team availability

#### Scenario: Existing corpus-only agent adopts the combined pack

- **WHEN** a member re-enables the resource pack in Simple and saves an existing corpus-only agent
- **THEN** conversation attachments become enabled alongside corpus access

#### Scenario: Advanced attachment override remains durable

- **WHEN** a member explicitly disables conversation attachments in Advanced, saves, then later edits and saves another field
- **THEN** attachments remain disabled while the combined pack still reflects the selected document-access capability

#### Scenario: Disable the combined pack

- **WHEN** a member switches off "Team resources" in Simple
- **THEN** the pack's document-access, reading, similarity, and tabular capabilities are withdrawn, while unrelated capability selections remain unchanged

#### Scenario: Template defaults enter the combined pack

- **WHEN** a new agent template preselects document access for a new agent
- **THEN** the form presents that selection under the combined pack and applies the combined defaults unless the member changes them in Advanced
