# Tabular Document Description Specification

## Purpose

Describe authorized tabular documents with classifications and types from extraction and column values from their queryable data when an agent requests them.

## Requirements

### Requirement: Numeric bounds are calculated when documents are described

For each authorized table selected through `describe_tabular_documents`, the system SHALL calculate `min_value` and `max_value` from that table's current queryable data for every integer and float column. It SHALL use finite non-null values only, and SHALL return null bounds when none exist. A description SHALL NOT depend on bounds stored in document metadata.

#### Scenario: Older workbook without stored bounds

- **WHEN** an agent describes a previously imported Excel document whose tables contain numeric values but whose metadata has no bounds
- **THEN** every numeric column in every selected table has the minimum and maximum from its queryable table data

#### Scenario: Mixed batch of CSV and Excel documents

- **WHEN** an agent describes authorized CSV and Excel documents in one call
- **THEN** each document retains its requested position, catalog and table descriptions, and each selected numeric column has bounds from its own table

#### Scenario: No finite numeric values

- **WHEN** a numeric column is empty, null throughout, or contains only non-finite values
- **THEN** its `min_value` and `max_value` are null

#### Scenario: Historical bounds differ from current table data

- **WHEN** stored bounds differ from the values in the queryable table
- **THEN** the description returns bounds calculated from the queryable table on that call

### Requirement: Categorical values are read when documents are described

CSV and Excel ingestion SHALL identify categorical string columns. For every selected column identified as categorical, `describe_tabular_documents` SHALL return its exact distinct non-null string values from its current queryable table data in `categorical_values`. It SHALL NOT use stored sample values as the source of the description. A non-categorical or temporal column SHALL omit `categorical_values`.

#### Scenario: Classified categorical column
- **WHEN** an agent describes a selected table containing a categorical string column
- **THEN** its `categorical_values` contains the exact distinct non-null categories, preserving stored spelling and case

#### Scenario: Older stored categories differ from table data
- **WHEN** stored category samples differ from the values in the queryable table
- **THEN** the description returns current categories instead of stored samples

#### Scenario: Current data has more categories than at classification
- **WHEN** a classified categorical string gains or loses values
- **THEN** its description returns all current distinct non-null categories, including an empty list if no non-null values remain

#### Scenario: Column not classified as categorical
- **WHEN** an agent describes a non-categorical column, including one with obsolete stored samples
- **THEN** its response omits `categorical_values`

### Requirement: Ingestion stores classification and type without description values

CSV and Excel ingestion SHALL retain column names, actual data types and the categorical verdict for string columns without persisting calculated category values or numeric bounds. It SHALL NOT calculate or persist the unused two-value verdict. Existing metadata containing legacy verdicts or samples SHALL remain readable. Describing a document SHALL NOT write calculated values back to document metadata.

#### Scenario: New import followed by description
- **WHEN** a CSV or Excel table is imported and then described
- **THEN** ingestion stores actual types and string classification without category lists, numeric bounds or the two-value verdict, and description reads current categories and numeric bounds from the selected tables

### Requirement: Description remains scoped and bounded

The system MUST authorize every requested document before reading its table data for category values or numeric bounds. These reads SHALL use the existing execution capacity, time, memory and cancellation limits. Only selected tables SHALL be scanned. The requested-document/catalog count SHALL independently remain bounded by the configured dataset budget, even when table selection excludes some documents. An unreadable selected table SHALL produce an explicit safe error rather than a partially populated successful description.

#### Scenario: Unauthorized document in a batch
- **WHEN** a description request includes a document the caller cannot read
- **THEN** the request fails before any category or numeric data from that document is read or returned

#### Scenario: Bound calculation cannot read an artifact
- **WHEN** a selected authorized table artifact cannot be read
- **THEN** the description fails without exposing a signed artifact URL or returning null bounds as if the table had no finite values

#### Scenario: Unreadable table without value columns
- **WHEN** a selected table has no numeric or classified categorical columns and its artifact cannot be read
- **THEN** the description fails explicitly instead of returning only its stored column schema

#### Scenario: Request exceeds the dataset scan limit
- **WHEN** the selected tables exceed the configured selected-dataset limit
- **THEN** the whole request is rejected before scanning any table

#### Scenario: Filtered schemas cannot bypass the catalog budget
- **WHEN** a table filter selects one table across more requested documents than the configured budget
- **THEN** the request is rejected before resolving or reading catalogs or table values

### Requirement: Description accepts explicit table selection

`describe_tabular_documents` SHALL accept an optional list of exact table names. Omission or an empty list SHALL describe every table as before. Names SHALL identify an existing SQL alias or an unambiguous exact sheet/title label within the requested documents. Unknown or ambiguous names SHALL fail explicitly before table-data reads. Selection SHALL retain the full workbook catalog and original document/table ordering without changing SQL aliases or document identifiers.

#### Scenario: No table filter
- **WHEN** the caller omits the table list or passes an empty list
- **THEN** every table of each authorized requested document is described

#### Scenario: Two relevant tables selected
- **WHEN** the caller selects Clients and Activite in a workbook where those labels uniquely identify tables
- **THEN** only those tables have detailed schemas and value scans while the complete catalog remains available

#### Scenario: Invalid or ambiguous label
- **WHEN** a selector is unknown or matches several tables
- **THEN** the call reports a safe selection error without reading table values or silently choosing another table

### Requirement: Column descriptions omit redundant fields

Public tabular column responses SHALL expose `name` and `dtype`, SHALL NOT expose `has_two_values`, `is_categorical` or `sample_values`, and SHALL use `categorical_values` only for categorical strings. `min_value` and `max_value` SHALL appear only on integer/float columns; numeric columns with no finite values SHALL retain null bounds. Unrelated nullable optional metadata SHALL be omitted. Current frontend consumers SHALL understand the new shape and continue displaying recorded historical responses.

#### Scenario: Identifier, category and datetime columns
- **WHEN** a response contains an identifier string, a categorical string and a datetime column
- **THEN** the identifier and datetime expose only name/type, the category additionally exposes its category list, and none exposes numeric bounds or removed fields

#### Scenario: Numeric range
- **WHEN** a selected numeric column is described
- **THEN** its bounds come from current finite values, or are null when none exist

#### Scenario: Historical trace
- **WHEN** a user opens a recorded response using the old category fields
- **THEN** the frontend still displays its stored schema without requiring the API to emit legacy fields

### Requirement: Temporal schema reflects preserved temporal data

Recognized unambiguous temporal columns SHALL remain physically temporal through ingestion, storage and SQL and SHALL use the API dtype `datetime`. Type conversion SHALL preserve non-empty source values and established timezone meaning. Ambiguous or incompatible mixed values SHALL NOT be silently discarded to satisfy date inference. No-coercion ingestion SHALL retain its configured behavior. Existing text artifacts SHALL remain described as strings until explicitly reprocessed.

#### Scenario: Excel native and unambiguous text dates
- **WHEN** a column of native Excel dates or consistently unambiguous date text is ingested with coercion enabled
- **THEN** its queryable artifact retains a temporal type and its schema reports `datetime` without a category list

#### Scenario: Invalid or ambiguous date text
- **WHEN** a column contains non-empty values that cannot safely share the inferred temporal interpretation
- **THEN** conversion does not silently replace those values with null or guess an ambiguous date meaning

#### Scenario: Existing stringified artifact
- **WHEN** an older artifact physically stores timestamps as text
- **THEN** it remains truthfully described as string until source reprocessing produces a temporal artifact
