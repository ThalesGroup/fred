## ADDED Requirements

### Requirement: Tabular tool descriptions distinguish references and SQL dialect

The tabular tool argument descriptions SHALL distinguish document UIDs from filenames and SQL table aliases. They SHALL direct the agent to reuse references from authorized discovery and identify DuckDB as the SQL dialect. Existing argument names, access rules and read-only validation SHALL remain unchanged. Opaque document identifiers MUST NOT acquire an assumed UUID format requirement.

#### Scenario: Model receives the tool schemas
- **WHEN** the runtime advertises description and query tools
- **THEN** document selector arguments explain that they expect discovered document UIDs
- **AND** the SQL argument explains that table aliases identify tables and that the query uses DuckDB

### Requirement: Tabular date guidance is concise and type-aware

The packaged instructions SHALL explain interval arithmetic for DATE/TIMESTAMP columns, conversion only when the source is text, and the unsupported SQLite-style two-argument `date` signature. They SHALL direct the agent to preserve exact categorical text values when constructing filters. The change SHALL add at most one compact date expression example and no more than 100 English words net to the existing tabular instructions.

#### Scenario: Add days to a typed date
- **WHEN** an agent needs to add seven days to a DATE/TIMESTAMP column
- **THEN** the instructions identify `date_column + INTERVAL '7 days'` as the applicable form
- **AND** they explain why `date(date_column, '+7 days')` is not a supported DuckDB function signature

#### Scenario: Timestamp-shaped value stored as text
- **WHEN** a discovered categorical string contains `2026-10-01 00:00:00`
- **THEN** the guidance directs the agent to use the exact stored string or an explicit appropriate date conversion
- **AND** it does not treat a successful empty result as an execution error requiring the unchanged query again
