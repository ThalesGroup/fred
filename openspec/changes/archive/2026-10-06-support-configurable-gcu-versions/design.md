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

### Preserve the applied revision and correct its final schema

The user already applied `a7e9c2d41063`; read-only local inspection confirmed that revision. Keep its enum conversion and parent unchanged. Add `e6b8d2a41074` after both it and the target's published `b4e8d2a9c613` identity revision to remove the intermediate history table without altering the current user version/timestamp. The final schema adds no tables or columns. This is the rare two-revision exception: collapsing the PR migration would change a revision already executed by the developer. Fresh and already-upgraded databases converge to the same single-version schema with one Alembic head. The corrective revision joins the two immutable parents; reparenting the locally applied revision would falsely imply that identity columns had already been added. This is the documented applied-revision exception to the usual linear-parent policy.

Downgrading the correction rebuilds history from current user records only; older discarded history requires a backup. The original downgrade guard still refuses before altering the enum when current values cannot be represented by `V1`.

### Preserve consumer boundaries

Pass the configured string directly through the acceptance service and expose `cguValidated: string | null`. Regenerate the frontend client with repository tooling. Keep first-acceptance default-team enrollment and service/asserted-user exemptions. Remove all added history ownership/startup dependencies from control-plane, knowledge-flow and runtime. Keep the charter regression test proving its separate per-version behavior.

## Risks / Trade-offs

- Old ORM readers cannot read arbitrary strings - stop shared readers and deploy updated backend versions together.
- Native PostgreSQL enums differ from SQLite - verify conversion and guarded rollback in an isolated PostgreSQL database.
- The old enum cannot represent a current newer acceptance - guarded downgrade or coordinated backup restoration is required.
- Only the latest GCU acceptance is retained - this is the user-requested original policy, and differs from charter history.

## Migration Plan

Back up the shared database, stop old readers, run control-plane Alembic upgrade, and start updated readers/frontend. Validate existing `v1` data and a real `v1 -> v2` acceptance. Roll back only if the current stored versions satisfy the downgrade guard or restore a coordinated backup. Operational details live in `docs/swift/ops/migrations/2972-configurable-gcu-versions.md`.
