## ADDED Requirements

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
