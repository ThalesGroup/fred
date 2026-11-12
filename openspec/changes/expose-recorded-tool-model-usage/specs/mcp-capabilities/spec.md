## ADDED Requirements

### Requirement: Tabular tool details expose recorded API model usage with explicit scope

Tabular tool details SHALL expose the exact input and output counters reported by the API for the model response that requested the tool, identifying their model-call scope rather than claiming isolated tool execution cost. Missing counters SHALL remain unavailable; explicit reported zero SHALL remain zero. The system MUST NOT derive these counters from character counts, tokenizers, neighboring requests or timing. Live events and stored history SHALL retain the same values and scope. Multiple tools requested by one response SHALL identify shared usage and MUST NOT multiply conversation billing totals. The existing status, duration and bounded syntax-colored result presentation SHALL remain available.

#### Scenario: Exact API counters survive reload
- **WHEN** an API model response reports input and output counters and requests a tabular tool
- **THEN** its tool details show those exact counters in the live conversation and after reload with the API-model scope explained

#### Scenario: Partial or absent usage
- **WHEN** a counter is missing, invalid or not recorded
- **THEN** the drawer identifies it as unavailable without inventing a number
- **AND** a valid explicitly reported zero is displayed as zero

#### Scenario: Shared model response
- **WHEN** one model response requests several tools
- **THEN** each associated tabular detail identifies that the counters cover the shared model response
- **AND** conversation billing counts that model response once

## MODIFIED Requirements

### Requirement: Tabular query details remain responsive for large returned payloads

Opening a supported tabular query step SHALL expose its recorded SQL and query status without first rendering or syntax-highlighting the full returned dataset. The initial response preview SHALL bound visible rows, columns and cell text and SHALL identify omitted data in one compact localized sentence, including complete-copy behavior when available. The bounded JSON preview SHALL retain the existing syntax colors and code-block presentation. Tool details MUST NOT invent token counts from payload character lengths. The original SQL and complete recorded response SHALL remain copyable without changing their contents. Oversized SQL SHALL receive a bounded visible preview with an explicit truncation indication and access to its complete original through copying. Live and reloaded traces SHALL use the same interpretation; opening a step SHALL NOT re-run its tool.

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
