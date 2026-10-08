## Purpose

Defines the two document sources an agent's `document_access` capability can use: files attached to the conversation and the team's documents. It covers how each source is configured, how legacy configs are read, and how the sources bound the chat controls, the registered tools and the document search.

## ADDED Requirements

### Requirement: Document access declares two positive sources

The `document_access` configuration SHALL expose two boolean source settings: `attachments` and `team_documents`. Both SHALL default to on. It SHALL NOT expose `show_attach_files_control` or `search_attachments_only` as configuration fields. A configuration with both sources off SHALL be rejected as invalid when it is saved.

#### Scenario: Defaults enable both sources

- **WHEN** an agent selects document access without any stored configuration
- **THEN** both attachments and team documents are enabled

#### Scenario: Both sources off is rejected on save

- **WHEN** a member saves an agent whose document access configuration has `attachments` and `team_documents` both off
- **THEN** the save is rejected with a configuration validation error and the stored agent is unchanged

#### Scenario: Saved configuration uses only the new keys

- **WHEN** an agent with document access is saved
- **THEN** its stored document access configuration contains `attachments` and `team_documents` and contains neither `show_attach_files_control` nor `search_attachments_only`

### Requirement: Legacy configurations are read through a compatibility mapping

A document access configuration that has neither `attachments` nor `team_documents` SHALL be read from the legacy keys, whether it is stored, submitted, copied or imported. It SHALL be mapped as follows:

- `show_attach_files_control` off: attachments off, team documents on.
- `show_attach_files_control` on and `search_attachments_only` on: attachments on, team documents off.
- `show_attach_files_control` on and `search_attachments_only` off or absent: both on.

An absent `show_attach_files_control` SHALL count as on, which was its default. When either new key is present, the legacy keys SHALL be ignored.

#### Scenario: Legacy corpus-only agent

- **WHEN** a stored configuration has `show_attach_files_control` off
- **THEN** the agent behaves with attachments off and team documents on, whatever `search_attachments_only` holds

#### Scenario: Legacy attachments-only agent

- **WHEN** a stored configuration has `show_attach_files_control` on and `search_attachments_only` on
- **THEN** the agent behaves with attachments on and team documents off

#### Scenario: Legacy full agent

- **WHEN** a stored configuration has `show_attach_files_control` on and `search_attachments_only` off
- **THEN** the agent behaves with both sources on

#### Scenario: New keys take precedence

- **WHEN** a configuration contains `team_documents` off and also a leftover `search_attachments_only` off
- **THEN** team documents stay off

#### Scenario: Next save rewrites a legacy configuration

- **WHEN** a member opens a legacy agent and saves it without touching document access
- **THEN** the stored configuration holds the mapped `attachments` and `team_documents` values and no legacy key

### Requirement: The attachments source controls the paperclip

The capability SHALL emit the file-attachment chat control only when `attachments` is on.

#### Scenario: Attachments on

- **WHEN** the composer controls are computed for an agent with attachments on
- **THEN** the file-attachment control is present

#### Scenario: Attachments off

- **WHEN** the composer controls are computed for an agent with attachments off
- **THEN** no file-attachment control is present

### Requirement: The team documents source controls corpus surfaces

When `team_documents` is off, the capability SHALL NOT emit the library or document scope picker, SHALL NOT apply its bound libraries, and SHALL NOT register the document tree listing tool. When `team_documents` is on, these surfaces SHALL follow their existing settings: the picker toggles, library binding, and bound library ids.

#### Scenario: Team documents off hides the scope picker and the tree

- **WHEN** an agent has team documents off and attachments on
- **THEN** no document scope control is emitted and only the document search tool is registered

#### Scenario: Stored library binding is inert without team documents

- **WHEN** an agent has team documents off and a stored library binding
- **THEN** the binding does not narrow any search and is kept in storage for when team documents is turned back on

#### Scenario: Team documents on keeps existing scope behavior

- **WHEN** an agent has team documents on with library binding enabled
- **THEN** the scope control pins the bound libraries and the document tree listing tool is registered, as before this change

### Requirement: Sources bound the document search

The document search SHALL include the conversation's attached files only when `attachments` is on, and the team corpus only when `team_documents` is on. The per-turn RAG scope selection SHALL only narrow these sources, never widen them. A "general knowledge only" turn SHALL run no document search. For a given pair of included scopes, the request sent to Knowledge Flow and the ranking of results SHALL be unchanged.

#### Scenario: Attachments-only agent never reaches the corpus

- **WHEN** an agent with attachments on and team documents off searches during a turn whose RAG scope is the default
- **THEN** only the conversation's attached files are searched

#### Scenario: Team-documents-only agent never reaches attachments

- **WHEN** an agent with team documents on and attachments off searches
- **THEN** only the team corpus is searched

#### Scenario: Per-turn scope narrows within the agent's sources

- **WHEN** an agent with both sources on searches during a turn whose RAG scope is "Your documents"
- **THEN** both the session attachments and team corpus are searched, and the answer uses document evidence without supplementation from general knowledge

#### Scenario: General knowledge only

- **WHEN** a turn's RAG scope is "General knowledge"
- **THEN** no document search is performed, whatever the agent's sources

### Requirement: Per-turn scope choices match the agent's sources

The RAG scope chat control SHALL offer document-only, combined and general-knowledge choices when either document source is enabled. The document-only choice SHALL be labelled "Documents only" in English and "Documents uniquement" in French, retaining the wire value `corpus_only`. Both document-only and combined choices SHALL search only sources enabled by the agent and the explicit per-turn scope flags.

#### Scenario: Attachments-only agent offers document-only answers

- **WHEN** the composer controls are computed for an agent with attachments on and team documents off
- **THEN** the document-only choice is offered and searches only session attachments

#### Scenario: Stored document-only default stays valid

- **WHEN** an attachments-only agent has a stored default RAG scope of `corpus_only`
- **THEN** the control preserves that default

### Requirement: The capability is presented as "Documents"

The user-facing name of the `document_access` capability SHALL be "Documents" in English and "Documents" in French. Its stored identifier SHALL remain `document_access`.

#### Scenario: Advanced card name

- **WHEN** a member opens the Advanced capabilities view in English or French
- **THEN** the document access card is titled "Documents"

### Requirement: Search uses explicit source keywords

The document search port and runtime adapter SHALL accept `include_attachments` and `include_team_documents` and SHALL NOT accept the removed `attachments_only` keyword. No alias resolver or deprecation-warning state SHALL remain. The migration note SHALL describe the immediate API break and replacement arguments.

#### Scenario: Caller uses the removed keyword

- **WHEN** a capability calls the runtime document search adapter with `attachments_only=True`
- **THEN** the call fails with an unexpected-keyword error before any search occurs

#### Scenario: Migrated attachments-only caller

- **WHEN** a capability calls with `include_attachments=True, include_team_documents=False`
- **THEN** no team corpus search occurs
