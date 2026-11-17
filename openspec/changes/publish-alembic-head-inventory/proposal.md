# Proposal

## Why

Operators cannot currently see the Alembic head of every component in a Fred release without inspecting several source trees or images. A release-scoped inventory gives them one reference for the expected migration targets.

Tracking: https://github.com/ThalesGroup/fred/issues/3571

## What Changes

- Generate a deterministic Markdown inventory containing only the head revision of each backend and capability migration tree at the tagged commit.
- Add the head table to both code and chart GitHub release descriptions, while keeping the existing operator migration guide attachment.
- Update the shared push-release skill and release documentation so the section is reviewed before tag approval and verified after publication.

## Capabilities

### New Capabilities

- `release-alembic-heads`: Publish a version-specific Alembic head inventory for operators.

### Modified Capabilities

None. The existing migration guide continues to describe operator actions; the new inventory records the head of each migration tree in the release.

## Impact

Release generation under `scripts/`, its focused tests, both tagged publication workflows, `.claude/skills/push-release/SKILL.md`, and `docs/swift/RELEASE-STRATEGY.md`. No database, migration script, application runtime, chart value, or image content changes are required.
