## Context

See [proposal.md](proposal.md). Repository-wide inspection found no application caller passing the enum; only the existing user-store test does so. The public exports and the store's input union are the remaining compatibility surface.

## Goals / Non-Goals

**Goals:** Make the Python input contract match the existing string storage contract.

**Non-Goals:** Change legal acceptance, admission, default-team enrollment, configuration, database schema or historical migrations.

## Decisions

Delete the class, both public reexports, enum imports and conversion. Annotate both store methods with `str` and persist `gcu_version` directly. Retaining a deprecated alias would preserve the compatibility the developer explicitly wants to retire; no replacement abstraction or runtime validator is needed.

Change the existing first-acceptance test input to `"v1"`; retain its arbitrary-version and state-preservation assertions and the concurrent-first-acceptance test. Verify downstream GCU acceptance and admission with their existing offline tests.

Keep published v3.2.0 migration notes and archived plans unchanged. Add a new note for this API retirement and extend the existing capability specification.

## Risks / Trade-offs

- External Python code importing `GcuVersionsType` will fail to import after upgrade. The migration note instructs those consumers to remove the import and pass strings. In-repository callers already do this.
- Existing deployments need no database or configuration operation. The new note uses `minor` operational impact because external Python client adaptation is conditionally required; historical enum-to-text upgrades and downgrade guards remain intact.

## Migration Plan

Adapt any external Python enum callers, then deploy normally. Rollback to v3.2.0 uses the usual deployment procedure; the database remains text in both versions.
