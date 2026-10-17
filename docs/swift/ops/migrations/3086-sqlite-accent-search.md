---
schema: 1
title: "Restore accent-insensitive user search on SQLite"
impact: none
no_action_reason: "Existing data, APIs and search semantics are preserved; normal deployment applies the SQLite query fix."
configuration: none
configuration_reason: "The SQLite SQL expression changes without changing configuration, schema or search semantics."
---
## Applicability

Fred services using SQLite for platform-access user search. PostgreSQL keeps its
existing `translate(lower(...))` expression.

## Prerequisites

None. No SQLite extension or connection-specific function is required.

## Configuration

No configuration or dependency change.

## Upgrade

Deploy the updated fred-core package with the consuming services. No database
migration or reindexing is needed. SQLite folding uses successive shallow common
table expressions instead of 161 nested replacements, avoiding parser stack
overflow on builds with a fixed parser stack.

## Validation

Search known users with accented and unaccented spellings, with and without the
individual-exception filter. Page results and totals must agree without HTTP 503.
The fred-core tests execute the complete folding table on SQLite and preserve the
PostgreSQL compilation contract.

## Rollback

Restore the previous package or service image. Data is unchanged, but the affected
SQLite builds again fail when searching users.

## Limitations

Case folding outside the supported accent table still follows the database's
`lower()` behavior. SQLite does not fold non-ASCII capitals outside that table.
