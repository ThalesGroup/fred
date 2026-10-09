## Context

See proposal.md for motivation. The current control-plane list returns bounded pages and a team-wide total without filters. `link_view` classifies rows as Revoked, then Expired, then Suspended when Link access is disabled, otherwise Active. Revocation retains the row and original recoverable URL. SQL mutations already serialize through the shared platform-access transaction. The frontend polls history every 30 seconds and uses generated RTK Query hooks.

## Goals / Non-Goals

**Goals:** Preserve lifecycle classification, team isolation and permissions while filtering full history and removing obsolete records atomically.

**Non-Goals:** No membership removal, admission-policy change, active-link deletion, scheduled cleanup, analytics retention system or schema migration.

## Decisions

1. **Filter on the server.** Add optional `status` (`active`, `revoked`, `expired`, `suspended`) to the existing list endpoint; omission means All. Use one UTC instant for predicates and returned classification, respecting existing priority. The matching total must use the same predicate. Client filtering of the loaded page would omit links and yield incorrect totals.
2. **Expose the cleanup count separately.** Extend the list response with `inactive_count`, counting the team's revoked-or-expired rows regardless of pagination and status filter. This enables a meaningful confirmation and disables cleanup when no obsolete rows exist. Counting only visible rows would misrepresent the operation.
3. **Use a dedicated cleanup endpoint.** Add `DELETE /admin/platform/access/teams/{team_id}/enrollment-links/inactive`, registered before the existing UUID deletion route. Require the existing platform Admin dependency, resolve the team and perform one team-scoped SQL delete under `store.mutation()`. Match `revoked_at IS NOT NULL OR expires_at <= now`; valid suspended rows are preserved. Return `deleted_count` and audit actor, team and count without token values. Repeating cleanup returns zero, not an error. Individual DELETE continues to mean revocation, so its behavior does not change.
4. **Reuse the shared controls.** Place a localized status Select beside the history actions, default All; changing it resets offset to zero and hides stale responses. Add a destructive "Delete expired and revoked links" button and a shared confirmation Dialog identifying the team, count and permanent removal of notes/counters. Cancel does nothing; errors preserve the filter/history. Busy states prevent overlapping mutations. Successful cleanup invalidates this team's history and resets offset to zero without resetting the filter. Existing Copy URL and Create link flows remain available.
5. **Evaluate eligibility at deletion time.** A link may expire while confirmation is open. The displayed count is a snapshot; the server deletes all eligible rows at execution time and the success receipt uses `deleted_count`. The operation always preserves currently valid links rather than trusting submitted IDs or statuses.

## Risks / Trade-offs

- Permanent history loss -> Confirm deletion explicitly and limit it to obsolete rows in the selected team. Membership remains untouched; removed URLs stay invalid.
- Races with enrollment, revocation or team changes -> Reuse the shared mutation transaction and server clock, testing lifecycle boundaries and rollback.
- Incorrect filtered totals or stale pages -> Share classification predicates, invalidate team-specific history and reset paging after filter/cleanup changes.
- Additional count query -> Keep database aggregation team-scoped without loading all links or tokens into application memory.

## Migration Plan

Regenerate the control-plane OpenAPI client with `make update-control-plane-api`. Deploy the API and frontend together; no migration or operator configuration is required. Rolling back the feature restores the previous listing but cannot restore deleted history without a database backup. Update the existing PR migration guide and product contract with that consequence.

The history table reuses the shared DataTable scroll body inside a 26rem container capped at 45dvh. Its header and pagination stay fixed. Retaining prior query totals during an uncached page request prevents DataTable from clamping the offset to zero; only current results supply rows.
