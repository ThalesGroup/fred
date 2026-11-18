## ADDED Requirements

### Requirement: Filled decks identify the acting user

PPT Filler SHALL set both Author and Last modified by in each newly filled PPTX to the acting user's trimmed first and last name when both are nonblank, or to the authenticated username when either is absent or blank. Each value SHALL be limited to 255 characters. When a trusted delegated identity has only a user ID, the generated PPTX SHALL use that ID rather than the template creator. The saved template and previously downloaded files SHALL remain unchanged.

#### Scenario: Complete name replaces template attribution

- **GIVEN** a template whose Author and Last modified by name its creator
- **WHEN** two authenticated users with different complete names fill it
- **THEN** each download names its own acting user in both properties
- **AND** the template retains its original properties

#### Scenario: Username fallback and property length

- **WHEN** an authenticated user fills a template with either name absent, empty, or whitespace
- **THEN** both properties use that user's username, truncated only beyond 255 characters

#### Scenario: Delegated identity without a profile name

- **WHEN** a trusted delegated user with only a verified user ID fills a template
- **THEN** both properties contain that ID, limited to 255 characters, rather than the template creator
