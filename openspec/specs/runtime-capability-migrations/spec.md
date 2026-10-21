# Runtime Capability Migrations Specification

## Purpose

Defines the operator-facing commands that advance or reverse the packaged fred-runtime and installed capability database migration trees.

## Requirements

### Requirement: Selected-tree one-step downgrade
The fred-runtime operational CLI SHALL accept `downgrade <tree> -1`, where `<tree>` is `runtime` or `capability:<id>` for an installed capability with migrations. It SHALL downgrade only that tree by one revision, using its own Alembic version table and the same database configuration as the upgrade command.

#### Scenario: Runtime tree is selected
- **WHEN** an operator runs `python -m fred_runtime downgrade runtime -1`
- **THEN** the runtime tree moves back one revision and every capability tree retains its revision

#### Scenario: Capability tree is selected
- **WHEN** an operator runs `python -m fred_runtime downgrade capability:writable_document -1`
- **THEN** only the writable-document tree moves back one revision

### Requirement: Explicit target and failure visibility
The downgrade command SHALL require an explicit tree and accept only the one-revision target `-1`. Missing or invalid targets and capability IDs without an installed migration tree SHALL fail before changing the database. An Alembic downgrade failure SHALL produce a nonzero result.

#### Scenario: Unsupported target
- **WHEN** an operator omits the tree, supplies a missing capability, or supplies a target other than `-1`
- **THEN** the CLI rejects the invocation without running a migration

#### Scenario: Selected tree fails
- **WHEN** the selected tree's downgrade raises an error
- **THEN** the CLI reports failure and no other tree is changed

### Requirement: Makefile parity with other backends
The `fred-agents` project SHALL provide `make db-downgrade MIGRATION_TREE=<tree>` to invoke the selected tree's one-revision downgrade, matching the one-step convention of the other backend projects. Its existing database upgrade path SHALL continue to upgrade fred-runtime and installed capability trees.

#### Scenario: Operator uses the Make target
- **WHEN** an operator runs `make db-downgrade MIGRATION_TREE=runtime` from `apps/fred-agents`
- **THEN** the runtime tree moves back one revision in the configured database and capability trees are unchanged

#### Scenario: Deployment applies migrations
- **WHEN** the existing deployment migration command runs
- **THEN** it still upgrades the fred-runtime tree and installed capability trees to their heads
