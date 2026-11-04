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

The tabular tool argument descriptions SHALL distinguish document UIDs from filenames and SQL table aliases. They SHALL direct the agent to reuse references from authorized discovery and identify DuckDB as the SQL dialect. Existing argument names, access rules and read-only validation SHALL remain unchanged. Opaque document identifiers MUST NOT acquire an assumed UUID format requirement.

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

A successful tabular query returning zero rows SHALL retain its SQL, empty `rows`, null `error` and dataset references, and SHALL include the message "Requête exécutée avec succès : 0 ligne correspondant aux conditions." The chat detail SHALL render the equivalent localized success explanation. Instructions SHALL direct the model to reuse successful results and inspect types and filters before changing an unexpectedly empty query. This change MUST NOT introduce result caching, duplicate-call suppression or new execution limits.

#### Scenario: No rows match the conditions
- **WHEN** an authorized SQL query completes with zero rows
- **THEN** its response includes the explicit zero-row success message and remains a successful tool result
- **AND** the model receives the structured query result and the chat shows an empty success rather than an error

#### Scenario: Aggregate returns a zero or null value
- **WHEN** a successful query returns an aggregate row containing zero or null
- **THEN** that row remains in the result and the response does not claim that zero rows were returned
