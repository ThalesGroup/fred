## Context

See [proposal.md](proposal.md) for the problem. Configuration accepts arbitrary GCU version strings, but the shared ORM/native PostgreSQL enum and acceptance service only allow `v1`.

The user requested keeping the original GCU behavior: `users` stores only the latest accepted version and timestamp. The earlier history-table design in this unmerged PR is superseded. Charter acceptance and its per-version storage remain unchanged.

## Goals / Non-Goals

**Goals:** Support configured version strings, preserve existing user data and admission/default-team policy.

**Non-Goals:** GCU history, additional tables or JSON columns, charter changes, new terms content configuration or admission exemptions.

## Decisions

### Keep the existing user columns

Change `gcuVersionAccepted` to nullable SQL text. Each acceptance replaces this value and `gcuAcceptedAt`, matching the original behavior. Admission reads the user row and compares the stored string exactly with configuration. User details return the stored version or null. Returning to an older version after accepting another version requires acceptance again.

Keep exported `GcuVersionsType.V1` only as a legacy store-input compatibility shim. Internal callers pass strings, model reads return strings, and external `.value` consumers must adapt. A single conflict-safe upsert updates only acceptance fields, preserving storage accounting and handling concurrent first acceptance without an additional table.

### Convert the existing column in one revision

The PR migration has not been deployed. Keep one revision, `a7e9c2d41063`,
reparented to the target's `b4e8d2a9c613` head. It only converts legacy enum name
`V1` to wire string `v1`, preserving nulls, timestamps, UUIDs, identity snapshots
and storage counters. PostgreSQL casts to text and drops the unused enum;
SQLite uses batch alteration. Create no tables or columns and no merge revision.

Downgrade refuses before changing schema or data if the current accepted string
cannot be represented by `V1`. An earlier local trial of the superseded PR
migration is a development schema-repair concern, handled separately after a
backup; it does not establish a deployed migration contract for the PR.

### Preserve consumer boundaries

Pass the configured string directly through the acceptance service and expose `cguValidated: string | null`. Regenerate the frontend client with repository tooling. Keep first-acceptance default-team enrollment and service/asserted-user exemptions. Remove all added history ownership/startup dependencies from control-plane, knowledge-flow and runtime. Keep the charter regression test proving its separate per-version behavior.

## Risks / Trade-offs

- Old ORM readers cannot read arbitrary strings - stop shared readers and deploy updated backend versions together.
- Native PostgreSQL enums differ from SQLite - verify conversion and guarded rollback in an isolated PostgreSQL database.
- The old enum cannot represent a current newer acceptance - guarded downgrade or coordinated backup restoration is required.
- Only the latest GCU acceptance is retained - this is the user-requested original policy, and differs from charter history.

## Migration Plan

Back up the shared database, stop old readers, run control-plane Alembic upgrade, and start updated readers/frontend. Validate existing `v1` data and a real `v1 -> v2` acceptance. Roll back only if the current stored versions satisfy the downgrade guard or restore a coordinated backup. Operational details live in `docs/swift/ops/migrations/2972-configurable-gcu-versions.md`.
