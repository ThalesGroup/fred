## ADDED Requirements

### Requirement: Built decks identify the acting user

PPT Builder SHALL set both Author and Last modified by in each newly built PPTX to the acting user's trimmed first and last name when both are nonblank, or to the authenticated username when either is absent or blank. Each value SHALL be limited to 255 characters. When a trusted delegated identity has only a user ID, the generated PPTX SHALL use that ID rather than the template creator. The chosen template and previously downloaded files SHALL remain unchanged.

#### Scenario: Complete name replaces template attribution

- **GIVEN** a template whose Author and Last modified by name its creator
- **WHEN** two authenticated users with different complete names build decks from it
- **THEN** each download names its own acting user in both properties
- **AND** the template retains its original properties

#### Scenario: Username fallback and property length

- **WHEN** an authenticated user builds a deck with either name absent, empty, or whitespace
- **THEN** both properties use that user's username, truncated only beyond 255 characters

#### Scenario: Delegated identity without a profile name

- **WHEN** a trusted delegated user with only a verified user ID builds a deck
- **THEN** both properties contain that ID, limited to 255 characters, rather than the template creator
