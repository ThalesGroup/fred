## Context

See `proposal.md` for motivation and `specs/platform-access-control/spec.md` for acceptance. `_t0_with_import_count` currently short-circuits on `t0_completed_at`. `set_user(..., grant=False)` deletes the individual grant; only the external audit stream retains its revocation. The shared `users` table has no creation timestamp from which to reconstruct old removals.

T0 already obtains paginated Keycloak identities through `PlatformAccessDirectory`, evaluates verified observations outside the policy mutation lock and serializes writes through `PlatformAccessStore.mutation()`. The activation dialog reads completed T0 status without a directory scan. Keep that inexpensive status path.

## Goals / Non-Goals

**Goals:** explicit refresh on the current administration surface, durable removal protection shared across replicas and compatibility with ordinary initial-import calls.

**Non-Goals:** automatic refresh on activation, startup or upgrade; removing existing grants during recalculation; rebuilding historical test data; changing admission rules or team membership; a removal-history browser.

## Decisions

### Extend the existing T0 routes

Add an optional typed `refresh_mode` to `GET .../t0-preview`, with `preserve_removals` and `include_removed` values. Without it, completed status stays cheap. With it, recompute missing candidates for the selected mode, return the policy revision and current completion time, and expose whether removal history is complete and how many recorded removals were skipped. Counts for refresh exclude people already holding a grant.

Add an optional Pydantic refresh body to `POST .../t0-import`, containing the explicit mode, expected policy revision and expected completed timestamp. An absent body retains the initial-import contract and completed-retry no-op. A refresh body requires a completed import and inactive filtering. Return actual additions alongside the existing completion fields; regenerate the client rather than hand-writing request types. A new endpoint family would duplicate the same import operation.

### Remember the latest individual removal

Add one control-plane-owned table keyed by user ID, recording the most recent individual removal time and actor. Upsert it atomically when an existing manual or T0 exception is removed. A no-op removal does not fabricate history. Keep this record when a person is explicitly re-added; it is a removal record, not an admission source. Preserve mode skips missing grants with a record; inclusion mode ignores those records. Existing grants always win and are never rewritten. A subsequent removal updates the record. Full event history remains in the existing audit stream.

Use a foreign key to `users.id` with cascade on identity deletion, matching individual-grant lifetime. The table is read only by administration operations, not per-request admission. This avoids making every request pay for the new feature. Reusing `platform_access_users` with a removal flag was considered: every admission query, listing and count would need a new predicate, and older readers would treat retained removed rows as active grants. Keeping the small removal table preserves that table's existing meaning and safe behavior for older readers.

Add a `t0_removal_history_complete` boolean to settings. New settings default to true. In the single migration, mark existing settings false when T0 already completed, true otherwise. False requires inclusion mode for the next explicit refresh; the API rejects preservation with a conflict indicating a required full refresh. Show a warning that history is unavailable, all T0 candidates will be recalculated and manually removed people can regain access. On successful full refresh, atomically set the flag true: this establishes a new baseline and intentionally supersedes unknown pre-upgrade removals. Cancellation or failure leaves it false. Do not infer removals from missing grants: that would also exclude legitimate newcomers.

Missing tables or columns require the normal migration first. The migration detects the legacy state and records the required reset; do not catch a live SQL schema error and attempt a partial import against an incompatible database. Existing grants stay intact during migration, and neither migration nor startup triggers an import.

### Keep snapshot and mutation boundaries explicit

Prepare directory and rule evaluation outside the policy lock. Under that same existing lock, recheck filtering, expected completion and policy revision, then read current grants and removal records, insert only eligible missing grants in bounded SQL batches and advance completion time atomically. Normalize completion timestamps for comparison and ensure a successful refresh advances the token even with zero additions. A stale refresh returns HTTP 409, with no success audit; replay cannot restore a grant removed after the original commit. Ordinary initial-import retries still return the completed state.

Directory changes between preview and confirmation can change actual additions because the POST recomputes the current population. Label preview counts as estimates and report the actual added count after success. A directory failure rolls back without treating an empty fallback as authoritative. Reuse `platform.access.t0.imported` with the selected mode and actual count, emitted once after commit.

### Offer the choice on every refresh

Keep the completed status and expose a small `2xs` refresh icon named "Refresh the whitelist" in Users while filtering is off, including after a later pause. Each opening starts on preservation mode when the completeness flag is true; otherwise inclusion is selected and preservation is unavailable. Switching mode requests a matching preview. Use the shared `Dialog` and existing selection controls. Explain that inclusion can restore access, and show the missing-history warning while the flag is false. Its wording must state that the next import recalculates the entire whitelist and can re-add manually removed people. Visible labels use whitelist/import wording without exposing the technical name T0. Cancel sends no mutation. While confirming, prevent duplicate submissions; a conflict requires refreshed state and another explicit confirmation. After success, refresh the whitelist, status and activation preview through existing cache invalidation and announce actual additions. Activation itself never starts an import.

## Risks / Trade-offs

- Legacy removals cannot be reconstructed reliably - require one confirmed full refresh with a missing-history warning; no production deployment used this feature according to the owner.
- An inclusion refresh can undo intentional removals - offer preservation first and explain the consequence before confirming inclusion.
- Large directories can make preview slow - fetch only for an open refresh dialog, retain provider pagination, off-thread classification and bounded writes; hold no database mutation lock across provider calls.
- Upgraded code reads a new settings column - apply the control-plane migration before upgrading participating readers; verify the existing schema guard reports incompatible state.

## Migration Plan

One linear control-plane Alembic migration creates the removal table, adds and initializes the completeness flag, and updates declared table ownership. Verify one head and a real upgrade on local PostgreSQL. Deploy the migration before new readers and writers. No configuration or chart value changes are needed.

Write a migration note with `impact: minor` for schema ordering and the required, explicitly confirmed full refresh on legacy test data. Roll back application code while retaining additive schema; record that removals performed by old code are not tracked, so returning to the new version after writes by old code requires marking completeness false and confirming a full refresh. Do not promise a downgrade that preserves removal protection after dropping the history.
