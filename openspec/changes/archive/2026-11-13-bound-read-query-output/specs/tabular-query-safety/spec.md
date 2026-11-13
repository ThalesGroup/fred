# Spec Delta

## ADDED Requirements

### Requirement: Query row limits distinguish omission from explicit null

`read_query` SHALL default an omitted `max_rows` to a deployment-configurable 500 rows. An explicit JSON null SHALL disable the tool-added row limit. Positive integers SHALL be accepted without a fixed server row ceiling. SQL-authored limits, authorization and execution budgets SHALL remain effective. Tool descriptions SHALL explain these semantics.

#### Scenario: Default preview
- **WHEN** the caller omits max_rows with default deployment settings
- **THEN** the tool applies a 500-row limit

#### Scenario: Explicit unlimited request
- **WHEN** the caller supplies max_rows as JSON null and SQL has no LIMIT
- **THEN** no tool-added row limit applies and the character budget still applies

#### Scenario: Large positive limit and invalid input
- **WHEN** the caller requests 5000 rows
- **THEN** no fixed server row ceiling reduces that request
- **AND** zero, negative limits and the string "none" remain invalid

#### Scenario: SQL-authored limit
- **WHEN** max_rows is null and the SQL includes LIMIT 20
- **THEN** at most 20 rows can be returned

### Requirement: Query data fits a configurable character budget

`read_query` SHALL retain the longest ordered prefix of complete rows whose serialized JSON array fits a deployment-configurable 50,000-character budget. Metadata and explanation text SHALL be additional to this budget. Rows and cells MUST NOT be cut or skipped. Unlimited row requests MUST NOT require materializing an unlimited result before applying this budget.

#### Scenario: Complete row boundary
- **WHEN** adding the next row would exceed the configured budget
- **THEN** only the preceding complete rows are returned in their original order
- **AND** valid JSON and success status are retained

#### Scenario: Equality and Unicode
- **WHEN** serialized rows contain escaped characters or Unicode and fit exactly at the configured character limit
- **THEN** they are retained without a character-truncation warning

#### Scenario: First row cannot fit
- **WHEN** the first row alone exceeds the budget
- **THEN** zero rows are returned with a truncation explanation and advice to select fewer columns or shorten large fields
- **AND** the result does not claim no rows matched

#### Scenario: Deployment override
- **WHEN** an operator supplies a character budget of at least 2 or a different positive default row limit through deployment values
- **THEN** the receiving backend applies those settings through its validated configuration

### Requirement: Partial SQL results carry tool-owned explanations

The tool SHALL place an English success message after returned row data when character truncation occurs or a finite tool row limit is reached. It SHALL distinguish a known result count from a reached limit, avoid fabricated totals, and explain character truncation as protecting model context while recommending more targeted queries. Supported displays SHALL preserve this tool-owned message.

#### Scenario: Known complete count before character truncation
- **WHEN** a 500-row request finds 300 rows and only 120 fit the character budget
- **THEN** the message states that 120 of the 300 matching rows were returned and explains the character limit

#### Scenario: Row limit and character budget both restrict output
- **WHEN** a 500-row request reaches 500 rows and only 120 fit the character budget
- **THEN** the message states that 120 of the 500 requested rows were returned, that further rows might match, and explains the character limit

#### Scenario: Reached row limit without character truncation
- **WHEN** all 500 returned rows fit the character budget and the requested 500-row limit is reached
- **THEN** the message states that 500 rows were returned and further rows might match

#### Scenario: Unlimited request reaches character budget
- **WHEN** max_rows is null and additional rows cannot fit the character budget
- **THEN** the message gives the returned row count and explains omitted data without claiming an uncomputed total

## MODIFIED Requirements

### Requirement: Empty SQL results remain explicit successes

A successful tabular query matching zero rows SHALL retain its SQL, empty `rows`, null `error` and dataset references, and SHALL include the message "Query executed successfully: 0 rows matched the conditions." The chat detail SHALL render the equivalent localized success explanation. Instructions SHALL direct the model to reuse successful results and inspect types and filters before changing an unexpectedly empty query. Zero rows caused by the character budget SHALL instead receive the truncation explanation. This change MUST NOT introduce result caching or duplicate-call suppression.

#### Scenario: No rows match the conditions
- **WHEN** an authorized SQL query completes with zero matching rows
- **THEN** its response includes the explicit zero-row success message and remains a successful tool result
- **AND** the model receives the structured query result and the chat shows an empty success rather than an error

#### Scenario: Aggregate returns a zero or null value
- **WHEN** a successful query returns an aggregate row containing zero or null and that row fits the character budget
- **THEN** that row remains in the result and the response does not claim that zero rows were returned
