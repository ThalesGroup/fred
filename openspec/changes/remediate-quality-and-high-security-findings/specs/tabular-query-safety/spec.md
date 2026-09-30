## Purpose

Allow agents to analyze selected tabular datasets with SQL while preventing access to other data sources, host resources, or runtime secrets through the query engine.

## ADDED Requirements

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
