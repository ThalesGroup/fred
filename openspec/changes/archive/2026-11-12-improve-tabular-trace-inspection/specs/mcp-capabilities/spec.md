## ADDED Requirements

### Requirement: Tabular query details remain responsive for large returned payloads

Opening a supported tabular query step SHALL expose its recorded SQL and query status without first rendering or syntax-highlighting the full returned dataset. The initial response preview SHALL bound visible rows, columns and cell text and SHALL identify omitted data. The original SQL and complete recorded response SHALL remain copyable without changing their contents. Oversized SQL SHALL receive a bounded visible preview with an explicit truncation indication and access to its complete original through copying. Live and reloaded traces SHALL use the same interpretation; opening a step SHALL NOT re-run its tool.

#### Scenario: Wide query response
- **GIVEN** a successful query result with hundreds of rows and dozens of columns
- **WHEN** the user opens its trace step
- **THEN** the drawer displays SQL above a bounded response preview and identifies the returned row count and preview limits
- **AND** initial rendered work does not grow with the total number of returned cells

#### Scenario: Oversized cell or SQL
- **WHEN** a query contains very long SQL or its result contains a very long cell
- **THEN** the visible preview is bounded and identifies truncation
- **AND** copying the SQL or recorded response preserves the complete original content

#### Scenario: Reopen, switch or stream
- **WHEN** a user opens a recorded query, switches to another step, reopens the query or receives unrelated streaming text
- **THEN** the drawer remains responsive and shows the selected call's SQL and preview without executing another query

#### Scenario: Failure and unknown-tool compatibility
- **WHEN** a failed supported tabular call or an unsupported tool is inspected
- **THEN** existing safe failure diagnostics and unknown-tool redaction remain in force

### Requirement: Tabular detail headers distinguish estimated input and output payload sizes

Supported tabular tool details SHALL show separately labelled input and output payload token estimates beside status and execution time. The input SHALL describe the recorded model-supplied arguments; output SHALL describe the complete recorded result content, independent of any visible preview. Labels and accessible help SHALL identify approximation and SHALL NOT describe these figures as billed model usage. Pending or absent content SHALL be identified as unavailable rather than zero. The display SHALL work with existing recorded trace parts and SHALL NOT modify conversation-level usage accounting. French and English labels SHALL convey the same meaning.

#### Scenario: Successful or failed supported tabular call
- **WHEN** a user inspects a supported tabular step with recorded arguments and a completed result
- **THEN** the header shows separate approximate input and output payload sizes beside its existing status and duration
- **AND** shortening the visible response preview does not change the output estimate

#### Scenario: Pending output versus empty output
- **WHEN** the tool result has not arrived or its content is absent
- **THEN** the output size is marked unavailable
- **WHEN** a completed result explicitly contains an empty string
- **THEN** the output size is zero

#### Scenario: Live and historical calls
- **WHEN** identical tabular call/result parts are inspected live or after reloading their conversation
- **THEN** both displays show the same estimates without requiring new persisted fields or another model/tool execution

#### Scenario: Other tools and conversation totals
- **WHEN** a user opens an unsupported tool or reviews conversation usage totals
- **THEN** no new per-tool estimate is shown for that unsupported tool and conversation billing/context totals retain their current meaning
