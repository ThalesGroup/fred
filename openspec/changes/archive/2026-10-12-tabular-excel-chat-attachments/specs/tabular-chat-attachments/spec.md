## Purpose

Lets an agent discover enabled corpus and conversation sources together and query complete attachment tables while preserving uploader privacy, conversation scope and older text-backed attachments.

## ADDED Requirements

### Requirement: New spreadsheet attachments expose complete queryable tables

A newly attached `.xls`, `.xlsx`, or `.xlsm` workbook SHALL expose every detected table from every supported sheet through the same tabular schema, search, and SQL operations as an Excel document in the corpus. The corpus-generated `output.md` SHALL be available in the tabular schema description as a roadmap to the workbook's sheets and tables. Its preview SHALL NOT be indexed as a competing, clipped vector document. The ingestion response SHALL report tabular availability.

#### Scenario: Multi-sheet workbook

- **WHEN** a user attaches a workbook with multiple detected tables and asks for rows beyond the fast preview limit
- **THEN** the agent can describe and query all tables, including the later rows and columns, under the attachment's document uid, and the schema description includes the workbook roadmap

#### Scenario: Unreadable or tableless workbook

- **WHEN** a new workbook cannot be parsed or has no queryable table
- **THEN** ingestion fails with an explicit client-visible error and leaves no successful attachment or orphaned table artifact

### Requirement: Attachment datasets remain private and erasable

A tabular attachment SHALL remain accessible only to its uploader or an authorized platform lifecycle operation. Discovery SHALL expose attachments only within the current authorized conversation and enabled attachment source. Unscoped dataset listings SHALL NOT enumerate attachments. Deleting the attachment SHALL remove its metadata and every table artifact.

#### Scenario: Owner queries an attached workbook

- **WHEN** the uploader requests schemas or a tabular query for an attached workbook uid
- **THEN** all its tables are available without requiring a corpus authorization tuple

#### Scenario: Another user names an attached workbook

- **WHEN** another user names that uid in a schema, search, or query request
- **THEN** no table data or dataset details are returned

#### Scenario: Attachment is deleted

- **WHEN** the attachment is removed by its owner or the platform lifecycle worker
- **THEN** its metadata and all table artifacts are removed

#### Scenario: Unscoped listing

- **WHEN** a dataset listing has no authorized conversation attachment scope, with ReBAC enabled or disabled
- **THEN** it does not enumerate attachment datasets, including other attachments owned by the caller

### Requirement: One listing discovers both enabled document sources

Calling `list_tabular_documents` without model-supplied scope arguments SHALL return the union of authorized corpus documents and ready tabular attachments of the current authorized conversation, constrained by enabled sources and active scope. Each document SHALL appear once by UID; same-name documents with different UIDs SHALL remain distinct. Each entry SHALL identify its origin as `corpus` or `conversation_attachment` and include corpus library names when available. CSV entries SHALL retain their compact document identity; Excel entries SHALL retain every detected table identity.

#### Scenario: Corpus and conversation both contain spreadsheets

- **WHEN** both sources are enabled and the conversation contains a ready CSV and a multi-table Excel attachment alongside accessible corpus spreadsheets
- **THEN** one no-argument listing returns both source classes with distinct origins, available corpus library names and all Excel table identities

#### Scenario: Same filename in two sources

- **WHEN** a corpus workbook and a conversation attachment have the same filename and different UIDs
- **THEN** the listing returns both documents with their own UIDs and origins

#### Scenario: Source ceiling and corpus selection

- **WHEN** discovery runs with source ceilings, turn source choices, personal/team scope or corpus library/document selections
- **THEN** the corpus branch honors those corpus restrictions, the attachment branch honors authorized conversation membership, and only enabled branches contribute entries
- **AND** corpus library selection does not discard enabled tagless conversation attachments, and model arguments cannot widen either branch

#### Scenario: No document source enabled

- **WHEN** neither document source is enabled, including a general-knowledge-only turn
- **THEN** discovery exposes neither corpus nor attachment entries

### Requirement: Conversation discovery validates membership and readiness

Attachment discovery SHALL validate current session ownership and persisted attachment membership in addition to uploader ownership. Model-supplied scope hints SHALL NOT establish authorization. Other conversations' attachments SHALL NOT be included, even when owned by the same uploader. Missing, deleted, unready or legacy text-only attachments SHALL NOT be advertised as ready SQL datasets. A failure to verify conversation membership SHALL produce an explicit failure rather than widen scope or silently report a complete inventory. Listing SHALL use bounded attachment resolution without an additional whole-catalog scan or table-data reads.

#### Scenario: Forged conversation or attachment identifier

- **WHEN** a model supplies another user's session or attachment identifiers, or an attachment from another conversation of the same user
- **THEN** no out-of-scope attachment names, UIDs, aliases or data are disclosed, with ReBAC enabled or disabled

#### Scenario: Attachment inventory changes

- **WHEN** an attachment is deleted, remains unready, has no queryable artifact or belongs to a previously used conversation
- **THEN** a fresh discovery excludes it and does not reuse another conversation's inventory

#### Scenario: Membership cannot be verified

- **WHEN** the authoritative conversation attachment lookup fails or refuses access
- **THEN** the agent receives an explicit discovery failure and no expanded attachment scope

### Requirement: Discovered documents remain usable under the same scope

Listing, schema description, SQL and value search SHALL enforce the same enabled source and conversation boundaries in an agent invocation. Corpus selectors SHALL NOT exclude an enabled conversation attachment from follow-up operations. Tabular instructions SHALL explain both origins once and guide a common list, describe and query flow, with schema inspection mandatory before SQL.

#### Scenario: Mixed-source follow-up

- **WHEN** an agent in ReAct or Deep discovers corpus and conversation spreadsheets within the active scope
- **THEN** their listed UIDs can be described and queried under that scope, including attachment rows beyond preview limits

#### Scenario: Explicit UID cannot bypass source boundaries

- **WHEN** an agent names a UID from a disabled source or an attachment outside the current authorized conversation in description, SQL or value search
- **THEN** the operation does not disclose its schema or data

### Requirement: Agent guidance reflects the attachment's stored representation

The agent SHALL use tabular tools for newly ingested CSV and Excel datasets and SHALL NOT treat a clipped preview as complete spreadsheet data. Older text-backed Excel attachments SHALL remain readable through their existing text path. A document reading tool called for a tabular-only attachment SHALL fail clearly or return an explicitly bounded preview; it SHALL NOT report a partial preview as a complete verbatim or exhaustive read.

#### Scenario: New Excel attachment is queried

- **WHEN** tabular tools are enabled and a user asks about an attached workbook
- **THEN** the agent is guided to describe and query the workbook's tables

#### Scenario: Legacy Excel attachment remains open

- **WHEN** a conversation includes an Excel attachment created before tabular ingestion was enabled
- **THEN** the agent can still use its text-backed representation without being told that an unavailable SQL dataset is the only path

#### Scenario: Reading tool is called on a tabular-only file

- **WHEN** verbatim, summary, or exhaustive extraction is requested for a tabular-only attachment
- **THEN** the result does not claim to have read the whole workbook or CSV from a preview
