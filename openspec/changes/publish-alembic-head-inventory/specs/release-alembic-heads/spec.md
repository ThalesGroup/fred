# Spec Delta

## Purpose

Provide operators with the Alembic head of each migration tree in a published Fred release.

## ADDED Requirements

### Requirement: Show one head for every shipped Alembic tree

Each Fred release description SHALL include a Markdown section for every backend and component Alembic migration tree shipped from its tagged source commit. The section MUST identify each tree's owner, path, and single head revision. It MUST NOT list historical revisions.

#### Scenario: Backend and capability migrations

- **WHEN** a release contains the control-plane backend, knowledge-flow backend, runtime, and capability Alembic trees
- **THEN** the inventory includes one head for each tree, with no historical revision list

#### Scenario: New component migration tree

- **WHEN** a later release adds a component with an Alembic migration tree
- **THEN** that component appears in the generated inventory without a manually maintained component list

### Requirement: Inventory reflects the published commit

The inventory SHALL be generated from the same commit as the paired `code/vX.Y.Z` and `chart/vX.Y.Z` tags. Generation MUST be deterministic, and publication MUST fail if a discovered tree contains duplicate revision identifiers, missing parent revisions, a cycle, or an ambiguous head.

#### Scenario: Repeated generation

- **WHEN** the inventory is generated twice from the same source commit and release version
- **THEN** both generated sections have identical content and tree ordering

#### Scenario: Invalid migration graph

- **WHEN** a migration tree has two heads or references a missing parent
- **THEN** the publication workflow stops before it publishes the release

### Requirement: Heads are visible in both release descriptions

The code and chart GitHub release descriptions SHALL each include the same version-specific Alembic head section. The existing operator migration guide SHALL remain attached. The shared release skill SHALL present the section before tag approval and verify its presence in both descriptions after publication.

#### Scenario: Paired release publication

- **WHEN** both tagged workflows complete for `X.Y.Z`
- **THEN** each GitHub release description shows the same Alembic heads for that version
