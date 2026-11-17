# Design

## Context

See proposal.md. Fred publishes paired code and chart tags from one commit. Both release workflows already attach a committed `migration.md`; Alembic trees currently live in two backends, `fred-runtime`, and two capability packages. The chart packages one deployment chart, while the code workflow builds several images.

## Goals / Non-Goals

**Goals:** Generate one complete inventory from tagged source with stable ordering and attach it to both GitHub releases. Make additions of new migration-bearing components visible automatically.

**Non-Goals:** Query a running database, infer which revisions an operator has applied, or prescribe upgrade and rollback operations. The existing operator guide owns those instructions.

## Decisions

### Generate at publication from the checked-out tag

Use a small repository script invoked in both `create-release` jobs, after checkout and before `action-gh-release`. Feed it the version derived from the tag and write `alembic-revisions.md` into the job workspace. The paired tag validation already ensures the tags identify one commit. Generating in CI avoids a committed, frequently stale copy and does not change image contents. Attaching a GitHub release asset makes the inventory directly downloadable; a loose file inside a Helm chart would be harder for operators to find.

### Discover migration trees and parse revision metadata without application imports

Find Alembic trees beneath `apps/` and `libs/` by their `env.py` and `versions/*.py`, and cross-check all `[tool.alembic]` project configurations. Fail when a configured tree is missing or uses unsupported version locations. Read the revision, down_revision, and description from the migration source without importing its application modules or connecting to a database. Reject unsupported dynamic metadata instead of silently omitting a revision. This keeps release jobs fast and independent of backend Python environments.

### Validate and order each graph

For each tree, validate unique revision IDs, local parent references, acyclicity, and exactly one head. Produce an oldest-to-newest topological order with stable tie-breaking, while preserving explicit parent IDs for merge revisions. Include the release version and source commit in the header. A local command and focused fixtures cover the current five trees and malformed graph cases.

## Risks / Trade-offs

- A migration tree with unusual metadata syntax or nonstandard version locations could fail publication. The failure is preferable to an incomplete inventory; focused fixtures and a run against the repository detect this before tagging.
- GitHub assets are separate from the OCI chart and images. The release skill will link the asset in the pre-tag review and confirm both publication results.

## Migration Plan

Add the generator, tests, workflow steps, skill instruction, and release strategy note in one reviewed PR. No database or deployment migration is needed. If publication must be rolled back, revert the workflow and skill change; already published inventory assets remain accurate for their tagged commits.
