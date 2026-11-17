# Spec Delta

## Purpose

Provide operators with a complete, trustworthy list of Alembic migrations included in each published Fred release.

## ADDED Requirements

### Requirement: Inventory every shipped Alembic tree

Each Fred release SHALL include a Markdown inventory of all Alembic revision files in every backend and component migration tree shipped from its tagged source commit. The inventory MUST group revisions by owning backend or component, identify each tree's head, and list every revision identifier, description, and parent revision.

#### Scenario: Backend and capability migrations

- **WHEN** a release contains the control-plane backend, knowledge-flow backend, runtime, and capability Alembic trees
- **THEN** the inventory includes each tree and all its revisions, including revisions unchanged since the preceding release

#### Scenario: New component migration tree

- **WHEN** a later release adds a component with an Alembic migration tree
- **THEN** that component appears in the generated inventory without a manually maintained component list

### Requirement: Inventory reflects the published commit

The inventory SHALL be generated from the same commit as the paired `code/vX.Y.Z` and `chart/vX.Y.Z` tags. Generation MUST be deterministic, and publication MUST fail if a discovered tree contains duplicate revision identifiers, missing parent revisions, a cycle, or an ambiguous head.

#### Scenario: Repeated generation

- **WHEN** the inventory is generated twice from the same source commit and release version
- **THEN** both files have identical content and revision ordering

#### Scenario: Invalid migration graph

- **WHEN** a migration tree has two heads or references a missing parent
- **THEN** the publication workflow stops before it publishes the release

### Requirement: Inventory is available with both release publications

The code and chart GitHub releases SHALL each attach the same version-specific Markdown inventory alongside the existing operator migration guide. The shared release skill SHALL present the inventory before tag approval and verify its presence on both releases after publication.

#### Scenario: Paired release publication

- **WHEN** both tagged workflows complete for `X.Y.Z`
- **THEN** each GitHub release offers the same inventory file for that version
