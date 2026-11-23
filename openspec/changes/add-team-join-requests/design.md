## Decisions

1. **Wire value `on_request`, not `request_only`.** Legacy bundles carry `request_only` as every team's old default; the importer keeps mapping it to `invite_only`, so no team opts in by accident.
2. **Public teams only.** A private team cannot be seen by a non-member; `update_team` stores `invite_only` for a private team.
3. **One row per (team, requester).** Pending expires after 30 days; refused stays 7 days (for "Accept anyway") and blocks asking again for 24 h. Accept and cancel delete the row; the audit log keeps the trail.
4. **Decisions go through the team routes.** Accept and refuse check `can_administer_members` server-side; tile buttons call them. Accept grants `team_member` first, then deletes the row, so a failed grant leaves the request to decide again.
5. **Recipients:** current team admins (`PERMISSION = can_administer_members`). The answer to the requester has no permission; it carries the team only when accepted.
6. **Leaving `on_request` refuses what is pending**, without the 24 h wait. Asking and this sweep share a per-team advisory lock.
7. **One membership hook.** Every grant or revoke runs `_on_team_access_changed`, which also deletes the person's request to that team.
8. **Decision tiles.** A payload class with `DECISION = True` has no close button and survives "Clear all" until handled; a failing call keeps the tile and shows a toast, a 404/403 removes it.
9. **The Requests tab never depends on notifications:** it polls and refetches on focus.

## Risks / Trade-offs

- An admin promoted after a request misses it in the bell; the Requests tab lists it.
- The not-a-member screen is UI only; server-side enforcement for platform admins is #3260.
