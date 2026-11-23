# Tabular Query Safety Specification

## Purpose

Allow agents to analyze selected tabular datasets with SQL while preventing access to other data sources, host resources, or runtime secrets through the query engine.

## Requirements

### Requirement: Agent SQL reads only authorized tabular datasets

The tabular query service SHALL accept a single read-only query over dataset aliases authorized for the caller. It SHALL reject statements, relation sources, and expressions that can access external files, networks, engine secrets, or runtime configuration outside those datasets.

#### Scenario: Authorized analytical query

- **WHEN** an agent submits a single SELECT query using DuckDB analytical functions over its authorized aliases
- **THEN** the service returns the query result within the existing row and execution budgets without requiring the functions in a static catalog

#### Scenario: Unauthorized relation or external source

- **WHEN** a query refers to an unselected dataset, external file, URL, table function, or engine metadata source
- **THEN** the service rejects it before releasing any data from that source

#### Scenario: Runtime configuration disclosure

- **WHEN** a query attempts to read engine settings or credentials through an expression
- **THEN** the service rejects it without returning configuration or credential data

#### Scenario: Side-effecting function

- **WHEN** a query invokes a DuckDB function whose engine metadata marks it as having side effects, or a macro that wraps such a function or an engine metadata source
- **THEN** the service rejects it before executing the query

### Requirement: Generated tabular SQL treats data as data

The service SHALL preserve the structure of internally generated statements when document names, column names, table names, search terms, or artifact locations contain SQL metacharacters. Invalid inputs SHALL fail safely without exposing signed artifact URLs.

#### Scenario: Metacharacters in generated-query inputs

- **WHEN** a selected document or search value contains quotes or SQL syntax
- **THEN** the operation either returns the intended data or rejects the input without executing the injected syntax

### Requirement: Pure built-in expressions retain their SQL compatibility

The tabular query service SHALL accept pure built-in analytical expressions over authorized datasets when the SQL parser adds the built-in's schema qualification. Qualification SHALL NOT exempt an expression from the existing inspection, side-effect, macro-dependency or source restrictions.

#### Scenario: String cleanup in an authorized audit

- **WHEN** an authorized read query uses `LOWER(TRIM(column))`, either `TRIM` syntax, or either `SUBSTRING` syntax on a text column
- **THEN** the query returns the expected values under the existing execution and row budgets

#### Scenario: Qualified safe built-in

- **WHEN** an expression resolves to an internal pure built-in in its trusted schema
- **THEN** schema qualification does not by itself cause rejection

#### Scenario: Qualification cannot bypass the security boundary

- **WHEN** a direct or nested expression uses an inspection function, unsafe macro, side-effecting or unknown function, unknown schema, explicit catalog, table source or unauthorized dataset
- **THEN** the service continues rejecting it before releasing data from the restricted source

### Requirement: Tabular tool descriptions distinguish references and SQL dialect

The descriptions of all four tabular tools SHALL state their purpose, prerequisites, expected inputs, returned data and relevant limits so the model can choose the correct operation. They SHALL distinguish successful empty results from errors and remain consistent with the packaged workflow. Argument descriptions SHALL distinguish document UIDs from filenames and SQL table aliases. They SHALL direct the agent to reuse references from authorized discovery and identify DuckDB as the SQL dialect. Existing argument names, access rules and read-only validation SHALL remain unchanged. Opaque document identifiers MUST NOT acquire an assumed UUID format requirement.

#### Scenario: Model receives the tool schemas
- **WHEN** the runtime advertises description and query tools
- **THEN** document selector arguments explain that they expect discovered document UIDs
- **AND** the SQL argument explains that table aliases identify tables and that the query uses DuckDB

### Requirement: Tabular date guidance is concise and type-aware

The packaged instructions SHALL explain interval arithmetic for DATE/TIMESTAMP columns, conversion only when the source is text, and the unsupported SQLite-style two-argument `date` signature. They SHALL direct the agent to preserve exact categorical text values when constructing filters. A global readability pass SHALL remove repetition and retain the discovery, mandatory schema inspection, source, CSV/Excel, alias, search and type rules. The revised prompt SHALL use at most one compact date expression example and SHALL NOT exceed the previous word count.

#### Scenario: Add days to a typed date
- **WHEN** an agent needs to add seven days to a DATE/TIMESTAMP column
- **THEN** the instructions identify `date_column + INTERVAL '7 days'` as the applicable form
- **AND** they explain why `date(date_column, '+7 days')` is not a supported DuckDB function signature

#### Scenario: Timestamp-shaped value stored as text
- **WHEN** a discovered categorical string contains `2026-10-01 00:00:00`
- **THEN** the guidance directs the agent to use the exact stored string or an explicit appropriate date conversion
- **AND** it does not treat a successful empty result as an execution error requiring the unchanged query again

### Requirement: Empty SQL results remain explicit successes

A successful tabular query matching zero rows SHALL retain its SQL, empty `rows`, null `error` and dataset references, and SHALL include the message "Query executed successfully: 0 rows matched the conditions." The chat detail SHALL render the equivalent localized success explanation. Instructions SHALL direct the model to reuse successful results and inspect types and filters before changing an unexpectedly empty query. Zero rows caused by the character budget SHALL instead receive the truncation explanation. This change MUST NOT introduce result caching or duplicate-call suppression.

#### Scenario: No rows match the conditions
- **WHEN** an authorized SQL query completes with zero matching rows
- **THEN** its response includes the explicit zero-row success message and remains a successful tool result
- **AND** the model receives the structured query result and the chat shows an empty success rather than an error

#### Scenario: Aggregate returns a zero or null value
- **WHEN** a successful query returns an aggregate row containing zero or null and that row fits the character budget
- **THEN** that row remains in the result and the response does not claim that zero rows were returned

### Requirement: Column diagnostics stay within the SQL's referenced scope

For supported unknown or ambiguous column failures, the curated `read_query` diagnostic SHALL identify the failing reference and provide bounded candidate columns only from authorized tables actually referenced and mounted by that SQL, and only when those columns are visible in the failing SQL scope. Diagnostics MUST NOT read, mount, inspect or disclose another table to suggest a correction, even when that table belongs to the same authorized workbook. Uncertain derived scopes SHALL retain a safe diagnostic without speculative candidates. Submitted SQL and authority-stop behavior SHALL remain unchanged, and the explanatory drawer SHALL retain arguments and error without a next-step section.

#### Scenario: Missing column with only one table referenced
- **WHEN** SQL reads Commandes as c and refers to c.region, while region exists only in an unreferenced Clients table
- **THEN** the diagnostic explains that region is absent from Commandes and may list a few of Commandes' available columns
- **AND** it neither mentions Clients nor reads its metadata or table data to produce suggestions

#### Scenario: Candidate in an explicitly joined table
- **WHEN** the failing SQL explicitly joins Clients as cl and region is visible there in the failing scope
- **THEN** the diagnostic may identify cl.region without loading another dataset or rewriting the query

#### Scenario: Ambiguous column
- **WHEN** a bare devise reference can refer to two explicitly joined tables
- **THEN** the diagnostic identifies their visible qualified column names without choosing a business meaning

#### Scenario: Derived or unauthorized scope
- **WHEN** a suggested source column is hidden by a CTE/subquery projection, the mapping cannot be proved, or a dataset is unauthorized
- **THEN** the diagnostic does not expose that column as a candidate or relax the access failure

### Requirement: Packaged SQL guidance prevents ambiguous and multi-statement calls

The packaged tabular system prompt SHALL direct the model to qualify columns by their table alias in JOIN queries and to send independent SQL instructions in separate tool calls. This clarification SHALL NOT change query execution, validation or error messages, add batch SQL support or introduce proposal 5's additional legacy-date/business-filter guidance.

#### Scenario: Join shares a column name
- **WHEN** two joined tables contain devise
- **THEN** the prompt directs the model to use a qualified reference such as c.devise according to the requested calculation

#### Scenario: Several independent calculations
- **WHEN** the model needs several independent SQL instructions
- **THEN** the prompt directs it to use separate tool calls with one instruction each

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
