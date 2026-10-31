---
name: psql
description: Inspect a requested Fred PostgreSQL schema, query or execution plan using the configured database connection. Read-only by default; does not assume a container, credentials or authorize live schema/data changes.
---

# Inspect PostgreSQL for a Fred increment

Follow `AGENTS.md` and `fred-reconstruction-method`. Establish the business
invariant before inspecting schema; do not infer the intended domain from tables.
Identify the actual checkout, target environment and database from the user's
request and current configuration/deployment instructions. Do not hardcode a
personal container, database name, password or production connection.

For Control Plane, start with `apps/control-plane/migrations/` and the generated
SQL reference in `docs/architecture/A2-manager-contracts.md`. Python components
may own Alembic histories; inspect their actual ownership. Applied migrations and
the live schema can differ from the checkout, so inspect history when relevant.

Use the configured client or container's `psql` without interactive TTY flags for
automation. Keep credentials out of chat, command arguments and captured output.
For read-only inspection, use a read-only transaction with bounded statement/lock
timeouts. Inspect catalog metadata first: tables, columns, keys, constraints,
indexes and migration versions. Do not dump user rows or documents unnecessarily.

For queries, identify row counts, selectivity, usable indexes, batching, lock
behavior and maintenance costs. Plain `EXPLAIN` is a plan estimate. `EXPLAIN
ANALYZE` executes the query; even reads can load the installation. Run it only
within an authorized experiment on an appropriate target. Prefer disposable
fixtures for experiments; a plan on them does not demonstrate production capacity.

A request to inspect a schema does not authorize writes, DDL, data resets,
constraint disabling or checksum changes. For requested mutations, establish the
specific scope, applied history, backup needs and transaction effects first.
Preserve existing guards and current concurrent work.

Report schema facts, assumptions, target environment, commands actually run and
what the evidence does or does not establish. Resolve ordinary SQL details without
asking the user to choose between technically equivalent options.
