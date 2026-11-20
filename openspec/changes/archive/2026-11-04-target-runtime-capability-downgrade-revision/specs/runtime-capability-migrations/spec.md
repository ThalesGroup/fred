## ADDED Requirements

### Requirement: Exact selected-tree downgrade
The fred-runtime operational CLI SHALL require a complete revision ID or `base` as the target of `downgrade <tree> <revision>`. It SHALL move only the selected installed runtime or capability tree to that target using its own version table and configured database. Relative targets such as `-1` SHALL be rejected.

#### Scenario: Runtime is downgraded across several revisions
- **WHEN** an operator selects `runtime` and supplies an older complete revision ID from that tree
- **THEN** the runtime tree reaches that revision without changing any capability version table

#### Scenario: New capability returns to base
- **WHEN** an operator selects an installed capability tree and supplies `base`
- **THEN** that capability tree returns to base without changing the runtime or other capability trees

## MODIFIED Requirements

### Requirement: Explicit target and failure visibility
The downgrade command SHALL require an explicit tree and a target of `base` or a complete revision ID from that selected tree. Missing trees or targets, relative targets, partial or unknown IDs, and capability IDs without an installed migration tree SHALL fail before changing the database. An Alembic downgrade failure SHALL produce a nonzero result.

#### Scenario: Unsupported target
- **WHEN** an operator omits the tree or target, supplies a missing capability, a partial or unknown revision ID, or a relative target such as `-1`
- **THEN** the CLI rejects the invocation without running a migration

#### Scenario: Selected tree fails
- **WHEN** the selected tree's downgrade raises an error
- **THEN** the CLI reports failure and no other tree is changed

### Requirement: Makefile parity with other backends
The `fred-agents` project SHALL require both `MIGRATION_TREE=<tree>` and `MIGRATION_REVISION=<revision>` for `make db-downgrade`. Its existing database upgrade path SHALL continue to upgrade fred-runtime and installed capability trees.

#### Scenario: Operator uses the Make target
- **WHEN** an operator runs `make db-downgrade MIGRATION_TREE=runtime` without `MIGRATION_REVISION`
- **THEN** the Make target rejects the command without running a migration

#### Scenario: Operator supplies an exact target
- **WHEN** an operator runs `make db-downgrade MIGRATION_TREE=runtime MIGRATION_REVISION=<older-runtime-revision>`
- **THEN** only the runtime tree reaches that revision

#### Scenario: Deployment applies migrations
- **WHEN** the existing deployment migration command runs
- **THEN** it still upgrades the fred-runtime tree and installed capability trees to their heads

## REMOVED Requirements

### Requirement: Selected-tree one-step downgrade
**Reason**: A relative `-1` target does not identify the recorded revision of an older release and can stop at the wrong schema.
**Migration**: Pass the complete old revision ID, or `base` for a capability tree that did not exist in the old release.
