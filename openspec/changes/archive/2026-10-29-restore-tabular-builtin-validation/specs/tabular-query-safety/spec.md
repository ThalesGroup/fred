## ADDED Requirements

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
