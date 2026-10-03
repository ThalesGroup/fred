## Purpose

Lets an agent query complete tables from conversation attachments while keeping each dataset inside the uploading user's access boundary and preserving older text-backed attachments.

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

A tabular attachment SHALL be accessible by explicit document uid only to its uploader or an authorized platform lifecycle operation. Blind dataset listings SHALL NOT reveal attachment datasets. Deleting the attachment SHALL remove its metadata and every table artifact.

#### Scenario: Owner queries an attached workbook

- **WHEN** the uploader requests schemas or a tabular query for an attached workbook uid
- **THEN** all its tables are available without requiring a corpus authorization tuple

#### Scenario: Another user names an attached workbook

- **WHEN** another user names that uid in a schema, search, or query request
- **THEN** no table data or dataset details are returned

#### Scenario: Attachment is deleted

- **WHEN** the attachment is removed by its owner or the platform lifecycle worker
- **THEN** its metadata and all table artifacts are removed

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
