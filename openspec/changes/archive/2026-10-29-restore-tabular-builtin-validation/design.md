## Context

See proposal.md. On the installed DuckDB build, `json_serialize_sql` returns `schema="main"` for unqualified `TRIM` and `SUBSTRING`. Both are internal scalar functions without side effects in the `main` schema. Fred's function validator currently rejects that schema. The same assumption occurs in macro dependency inspection.

The existing pending `tabular-query-safety` delta owns the overall security contract. This follow-up adds only compatibility acceptance and must be reconciled with that capability before archival.

## Goals / Non-Goals

**Goals:** Restore these valid analytical queries while proving that qualification cannot bypass the existing security boundary.

**Non-Goals:** Change model behavior, interpret business rules, increase query row/context budgets, change the MCP protocol, or support caller-defined functions.

## Decisions

- Derive trusted function identities from the clean in-memory built-in catalog, including schema and existing purity checks. Accept empty qualification only for safe default-resolution names; accept a qualified expression only when its identity resolves to that trusted set. Continue rejecting explicit catalogs and unknown schemas.
- Preserve the inspection denylist and transitive macro checks. Apply compatible identity handling to macro dependencies so pure wrappers are not incorrectly classified, without allowing macros that inspect settings, read relations or invoke side effects.
- Retain conservative purity by function name across internal overloads and schemas: one unsafe implementation excludes that name everywhere. Qualified identities must exist in the clean catalog; unqualified identities are included only for the engine's default search schemas.
- Keep existing relation validation, exact Parquet path restrictions, row limits and worker admission/cancellation unchanged. A blanket allowance for `main` is rejected because a schema alone is not evidence of purity.
- Cache immutable catalog metadata per process as today. No per-query network/database lookup, cross-request coordination, new lock or table is needed. Every pod derives the same policy from its pinned engine build.

## Risks / Trade-offs

- [Expanded SQL acceptance] Qualification can otherwise bypass the purity filter. Verify direct and nested inspection calls, unsafe macros, table functions, unknown names/schemas/catalogs and unauthorized relations alongside positive cases.
- [Engine changes] Parser rewriting and built-in metadata can change with DuckDB upgrades. Run real parser and restricted-execution regressions using the installed pinned version.
- [Audit accuracy] Passing SQL tests cannot establish model reasoning quality. Keep the Small/Large comparison evidence distinct from platform tests; the original prompt forbids translating rules into SQL and the campaign has contradictory expected text for REG-001/003.

## Migration Plan

Normal Knowledge Flow rollout after approval and verification; no re-ingestion or persistent migration. Rollback restores the old validator and its compatibility defect. The local API currently runs without reload, so live post-fix validation requires coordinating its restart first.
