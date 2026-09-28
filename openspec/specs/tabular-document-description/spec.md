# Tabular Document Description Specification

## Purpose

Describe authorized tabular documents with classifications and types from extraction and column values from their queryable data when an agent requests them.

## Requirements

### Requirement: Numeric bounds are calculated when documents are described

For each authorized document requested through `describe_tabular_documents`, the system SHALL calculate `min_value` and `max_value` from the document's current queryable table data for every integer and float column. It SHALL use finite non-null values only, and SHALL return null bounds when none exist. A description SHALL NOT depend on bounds stored in document metadata.

#### Scenario: Older workbook without stored bounds

- **WHEN** an agent describes a previously imported Excel document whose tables contain numeric values but whose metadata has no bounds
- **THEN** every numeric column in every table has the minimum and maximum from its queryable table data

#### Scenario: Mixed batch of CSV and Excel documents

- **WHEN** an agent describes authorized CSV and Excel documents in one call
- **THEN** each document retains its requested position, catalog and table descriptions, and each numeric column has bounds from its own table

#### Scenario: No finite numeric values

- **WHEN** a numeric column is empty, null throughout, or contains only non-finite values
- **THEN** its `min_value` and `max_value` are null

#### Scenario: Historical bounds differ from current table data

- **WHEN** stored bounds differ from the values in the queryable table
- **THEN** the description returns bounds calculated from the queryable table on that call

### Requirement: Categorical values are read when documents are described

CSV and Excel ingestion SHALL identify categorical string columns. For every column identified as categorical, `describe_tabular_documents` SHALL return its exact distinct non-null string values from its current queryable table data. It SHALL NOT use stored sample values as the source of the description. A non-categorical column SHALL have no category samples in the description.

#### Scenario: Classified categorical column

- **WHEN** an agent describes a table with a string column classified as categorical
- **THEN** that column's `sample_values` contains its exact distinct non-null categories from the queryable table

#### Scenario: Older stored categories differ from table data

- **WHEN** stored category samples differ from the values in the queryable table
- **THEN** the description returns the categories read from the queryable table on that call

#### Scenario: Current data has more categories than at classification

- **WHEN** the Parquet table gains distinct values after its string column was classified as categorical
- **THEN** the description returns all current distinct non-null values while retaining the stored categorical verdict

#### Scenario: Column not classified as categorical

- **WHEN** an agent describes a string column not classified as categorical
- **THEN** its description has no category samples, including when older metadata contains samples

### Requirement: Ingestion stores classification and type without description values

CSV and Excel ingestion SHALL retain column names, numeric types, and the categorical and two-value verdicts for string columns without persisting calculated category samples or numeric bounds. Describing a document SHALL NOT write its calculated values back to document metadata.

#### Scenario: New import followed by description

- **WHEN** a CSV or Excel table with categorical and numeric columns is imported and then described
- **THEN** its stored schema contains the categorical verdict and numeric types without sample values or numeric bounds, while the description contains categories and bounds read from the table

### Requirement: Description remains scoped and bounded

The system MUST authorize every requested document before reading its table data for category samples or numeric bounds. These reads SHALL use the tabular execution capacity, time, memory and cancellation limits. An unreadable table SHALL produce an explicit safe error rather than a partially populated successful description.

#### Scenario: Unauthorized document in a batch

- **WHEN** a description request includes a document the caller cannot read
- **THEN** the request fails before any category or numeric data from that document is read or returned

#### Scenario: Bound calculation cannot read an artifact

- **WHEN** an authorized document's table artifact cannot be read
- **THEN** the description fails without exposing a signed artifact URL or returning null bounds as if the table had no finite values

#### Scenario: Unreadable table without value columns

- **WHEN** an authorized table has no numeric or classified categorical columns and its artifact cannot be read
- **THEN** the description fails explicitly instead of returning only its stored column schema

#### Scenario: Request exceeds the dataset scan limit

- **WHEN** the requested documents contain more tables than `max_selected_datasets`
- **THEN** the description rejects the whole request before scanning any table
