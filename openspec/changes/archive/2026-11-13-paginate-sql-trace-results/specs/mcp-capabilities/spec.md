## MODIFIED Requirements

### Requirement: Tabular query details remain responsive for large returned payloads

Opening a supported tabular query step SHALL expose its recorded SQL and query status without first rendering or syntax-highlighting the full returned dataset. The initial response preview SHALL show up to ten rows with every returned column and complete column names, while bounding long cell text, and SHALL identify omitted data in one compact localized sentence, including complete-copy behavior when available. When recorded rows remain hidden, a small localized action below the JSON preview SHALL reveal the next ten rows, or the remaining rows if fewer than ten remain, retaining the already visible rows. The action SHALL state the actual next row count and disappear when every recorded row is visible. The preview SHALL retain the existing syntax colors and code-block presentation. Tool details MUST NOT invent token counts from payload character lengths. The original SQL and complete recorded response SHALL remain copyable without changing their contents. Oversized SQL SHALL receive a bounded visible preview with an explicit truncation indication and access to its complete original through copying. Live and reloaded traces SHALL use the same interpretation; opening or expanding a step SHALL NOT re-run its tool, fetch additional database rows or change the recorded response and its tool-owned notices.

#### Scenario: Wide query response
- **GIVEN** a successful query result with hundreds of rows and dozens of columns
- **WHEN** the user opens its trace step
- **THEN** the drawer displays SQL above a response preview and identifies the returned row count and preview limits
- **AND** all returned columns are visible for each of the first ten rows
- **AND** initial rendered work does not grow with the number of rows beyond those ten preview rows

#### Scenario: Progressive inspection
- **GIVEN** a recorded successful query with 25 rows
- **WHEN** the user opens its step and chooses the reveal action twice
- **THEN** the visible rows progress from 10 to 20 to 25, preserving row order and every column
- **AND** the first action announces ten additional rows, the second announces five, and no action remains after the final rows appear
- **AND** the existing syntax-colored JSON presentation, full-response copying, status and duration remain available

#### Scenario: Short or empty result
- **WHEN** a successful query contains at most ten recorded rows, including zero
- **THEN** all recorded rows are initially visible without a reveal action
- **AND** the existing empty-result interpretation and tool-owned result notices remain intact

#### Scenario: Oversized cell or SQL
- **WHEN** a query contains very long SQL or its result contains a very long cell
- **THEN** the visible preview is bounded and identifies truncation
- **AND** copying the SQL or recorded response preserves the complete original content, including rows that have not been revealed

#### Scenario: Reopen, switch or stream
- **WHEN** a user opens a recorded query, switches to another step or reopens the query
- **THEN** the selected call starts with at most ten rows without executing another query
- **AND** expansion from another call does not carry over, even if its SQL is identical
- **WHEN** unrelated streaming text arrives while the same call is expanded
- **THEN** its current visible row count and preview remain stable

#### Scenario: Recorded result is already limited by the tool
- **WHEN** a recorded response contains a tool-owned truncation notice and hidden preview rows
- **THEN** expanding the preview reveals only rows present in that response
- **AND** the notice remains visible without implying that additional database rows were fetched

#### Scenario: Failure and unknown-tool compatibility
- **WHEN** a failed supported tabular call or an unsupported tool is inspected
- **THEN** existing safe failure diagnostics and unknown-tool redaction remain in force
- **AND** no SQL-result reveal action is introduced for those states

### Requirement: Tabular details do not attribute full model usage to an individual tool

The tabular tool drawer MUST NOT label a model request's complete prompt or completion counters as tokens sent or received by an individual tool. This applies to requesting, following and historical model-response metadata, including shared tool batches. The drawer SHALL omit per-tool token counters rather than substitute global model usage, derive an estimate or claim zero consumption. The drawer SHALL retain status, duration, SQL, bounded syntax-colored results and complete supported-copy behavior, without an added model-usage explanation paragraph.

New tool-call/final events and newly written history SHALL NOT include the dedicated `model_call_usage` attribution introduced for tool-token display. Established accumulated `token_usage` and final `context_tokens` SHALL retain their conversation-accounting meaning. Historical messages containing retired optional attribution metadata SHALL remain readable without a database rewrite.

#### Scenario: One returned row and large model context
- **GIVEN** a tabular query returns one row without tool-specific API usage
- **AND** the following model response reports 59260 input and 12426 output tokens
- **WHEN** the user opens the tool details
- **THEN** no tool token badges display those global model counters
- **AND** the status, duration, SQL and returned row remain available without a model-usage explanation paragraph

#### Scenario: Live updates and reload
- **WHEN** model-call usage arrives after a tool result or the conversation is reloaded with model usage metadata
- **THEN** the tool drawer does not reinterpret that metadata as an individual tool's consumption

#### Scenario: Missing or zero model usage
- **WHEN** model metadata has missing, invalid or zero counters but no tool-specific API breakdown exists
- **THEN** no estimated, unavailable-placeholder or zero-valued tool consumption badge is displayed

#### Scenario: Shared model response
- **WHEN** one model exchange includes results from several tools
- **THEN** its full request and response usage is not presented as the consumption of each tool
- **AND** existing conversation accounting remains unchanged


#### Scenario: Retired attribution and preserved accounting
- **WHEN** the runtime executes sequential or parallel tool calls and writes the completed turn
- **THEN** new tool-call and final events and history omit dedicated model-call attribution metadata
- **AND** aggregate model usage, cache accounting and final context counters remain available through their established fields
- **WHEN** an older recorded message contains retired optional attribution metadata
- **THEN** its content remains readable without restoring tool token badges or requiring backfill
