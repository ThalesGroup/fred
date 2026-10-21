## Purpose

Defines the operator-facing commands that advance or reverse the packaged fred-runtime and installed capability database migration trees.

## ADDED Requirements

### Requirement: One-step combined downgrade
The fred-runtime operational CLI SHALL accept `downgrade -1` and downgrade each installed capability migration tree by one revision in reverse discovery order, then downgrade the fred-runtime tree by one revision. Each tree SHALL use its own Alembic version table and the same database configuration as the upgrade command.

#### Scenario: Runtime and capability trees are at head
- **WHEN** an operator runs `python -m fred_runtime downgrade -1`
- **THEN** each installed capability tree moves back one revision before the fred-runtime tree moves back one revision

#### Scenario: A capability has no migration tree
- **WHEN** an installed capability does not supply migrations
- **THEN** the command skips that capability and continues with the remaining trees

### Requirement: Explicit target and failure visibility
The combined downgrade command SHALL accept only the one-revision target `-1`. Invalid or missing targets SHALL fail before changing the database. If a tree's downgrade fails, the command SHALL return a nonzero result and SHALL NOT start any later tree; previously completed trees SHALL retain their resulting revisions.

#### Scenario: Unsupported target
- **WHEN** an operator supplies no target or a target other than `-1`
- **THEN** the CLI rejects the invocation without running a migration

#### Scenario: One tree fails
- **WHEN** a capability tree's downgrade raises an error
- **THEN** the CLI reports failure and does not downgrade the trees that follow it

### Requirement: Makefile parity with other backends
The `fred-agents` project SHALL provide `make db-downgrade` to invoke the combined one-revision downgrade, matching the one-step convention of the other backend projects. Its existing database upgrade path SHALL continue to upgrade fred-runtime and installed capability trees.

#### Scenario: Operator uses the Make target
- **WHEN** an operator runs `make db-downgrade` from `apps/fred-agents`
- **THEN** the combined downgrade uses the project's configured database and moves each participating tree back one revision

#### Scenario: Deployment applies migrations
- **WHEN** the existing deployment migration command runs
- **THEN** it still upgrades the fred-runtime tree and installed capability trees to their heads
