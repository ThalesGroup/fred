# Proposal

## Why

Operators cannot currently see which Alembic revisions ship in each Fred release without inspecting several source trees or images. A release-scoped inventory gives them a single, reviewable reference for database upgrade planning and troubleshooting.

Tracking: https://github.com/ThalesGroup/fred/issues/3571

## What Changes

- Generate a deterministic Markdown inventory of every Alembic revision in each backend and capability migration tree at the tagged commit, including the head revision for each tree.
- Attach the inventory to both the code and chart GitHub releases alongside the existing operator migration guide.
- Update the shared push-release skill and release documentation so the inventory is reviewed before tag approval and verified after publication.

## Capabilities

### New Capabilities

- `release-alembic-inventory`: Publish a complete, version-specific Alembic revision inventory for operators.

### Modified Capabilities

None. The existing migration guide continues to describe operator actions; the new inventory records the revisions included in the release.

## Impact

Release generation under `scripts/`, its focused tests, both tagged publication workflows, `.claude/skills/push-release/SKILL.md`, and `docs/swift/RELEASE-STRATEGY.md`. No database, migration script, application runtime, chart value, or image content changes are required.
