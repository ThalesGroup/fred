## ADDED Requirements

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

A successful tabular query returning zero rows SHALL retain its SQL, empty `rows`, null `error` and dataset references, and SHALL include the message "Requête exécutée avec succès : 0 ligne correspondant aux conditions." The chat detail SHALL render the equivalent localized success explanation. Instructions SHALL direct the model to reuse successful results and inspect types and filters before changing an unexpectedly empty query. This change MUST NOT introduce result caching, duplicate-call suppression or new execution limits.

#### Scenario: No rows match the conditions
- **WHEN** an authorized SQL query completes with zero rows
- **THEN** its response includes the explicit zero-row success message and remains a successful tool result
- **AND** the model receives the structured query result and the chat shows an empty success rather than an error

#### Scenario: Aggregate returns a zero or null value
- **WHEN** a successful query returns an aggregate row containing zero or null
- **THEN** that row remains in the result and the response does not claim that zero rows were returned
