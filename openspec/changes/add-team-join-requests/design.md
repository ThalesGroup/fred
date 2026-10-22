## Context

Full rationale and catalogue: `docs/swift/rfc/NOTIFICATIONS-RFC.md` (types 3 and 4). This change builds on the notification framework of `add-in-app-notifications` (same branch) without changing its store or API.

What exists today (audit of `origin/swift` and `feat/notifications`, 2026-10-22):

- `JoiningMode` (`libs/fred-core/fred_core/teams/metadata_store.py`): `open`, `invite_only`, stored in `teammetadata.joining_mode` as `String(20)`, so a new value needs no DDL. `TeamVisibility` is independent; a private team has no `public` relation, so a non-member cannot read it at all. `update_team` downgrades `open` to `invite_only` when the result would be private.
- Self-service join: `join_team` (`POST /teams/{team_id}/join`), checks `joining_mode == OPEN`, grants `team_member` to the caller only. Admin add: `add_team_member` (gated by the permission matching the role, `can_administer_members` for `team_member`). Team invite link (#3116, `platform_access/service.py` `enroll`) grants `team_member` through a link.
- Discovery: `MarketplaceTeams` lists public non-member teams under "Other teams"; `TeamCard` shows "Join" for `open` and the static label "Invite only" otherwise. A non-member card is not a link. The access-denied pages (#3085) are about platform access, not about a team, and a private team is invisible to non-members, so neither offers a better entry point.
- Mode chooser: `TeamSettingsParameters` (ButtonGroup `open` / `invite_only` for public teams, a locked "manual only" button for private ones).
- `can_administer_members` = `team_admin` (`schema.fga`); `pending_team_admin` (charter not accepted) does not hold it.
- No request-like table exists. `platform_access_links` is about links, not requests.
- Notifications: `ACTION_PERMISSION` (`notifications/schemas.py`) maps each type to a `TeamPermission`; `_allowed_recipients` skips drafts without `team_id`; `forget_lost_access` iterates `ACTION_PERMISSION.values()`; `resolve` deletes the actor's own open rows and marks the others handled. The frontend registry (`rework/features/notifications/notificationTypes.ts`) already has `kind: "call"` actions, unused until now.

## Goals / Non-Goals

**Goals:** a person can ask to join a public `on_request` team from its card; its current admins get an actionable notification; the first decision wins; the requester gets the answer; nothing changes for teams that do not opt in.

**Non-Goals:** requests to private teams, email, a request history screen, a role other than `team_member`, request rate limiting beyond decision 5.

## Decisions

1. **Wire value `on_request`, not a revived `request_only`.** Legacy bundles carry `request_only` as the old default of every team (migration `a4b5c6d7e8f9` moved all teams there). Reusing it would make an old import turn requests on for teams whose admins never chose them, against the owner's "opt-in" rule. The importer keeps `request_only → invite_only` and passes `on_request` through. Labels: "On request" / "Sur demande".
2. **Public teams only.** Same rule as `open`: the ButtonGroup offers Open / On request / Invite only for a public team; a private team keeps the locked "manual only" button, and `update_team` turns `on_request` into `invite_only` when the result is private. A non-member cannot see a private team, so a request mode there would have no entry point; the team invite link already covers it.
3. **Requester entry point: the existing `TeamCard` in "Other teams".** It is where the person already learns the mode. States: no request → "Ask to join" (opens the shared `Dialog` with an optional message, `TextArea` with its guidance in `description`); pending → label "Request sent" and a text button "Cancel request"; refused → label "Request declined". The caller's own requests come from `GET /teams/join-requests/mine`, fetched once by `MarketplaceTeams` and passed down, so the hot team listing (`_list_teams`) is untouched.
4. **Record: one row per (team, requester), only while it matters.** Table `team_join_requests`: `id`, `team_id`, `requester_id`, `requester_name` (display snapshot), `message` (nullable, at most 280 characters, plain text), `status` (`pending` | `refused`), `created_at`, `expires_at` (= `created_at` + 30 days, the notification expiry), `decided_at`, `decided_by`. Unique `(team_id, requester_id)`; indexes on `requester_id` and `expires_at`. Accept and cancel delete the row (the audit log keeps the trail); refuse keeps it until `expires_at`. Every read ignores expired rows; a new request replaces an expired one; the lifecycle notification step also deletes expired requests in the same budget.
5. **Duplicates and abuse.** A second ask while pending answers 200 with the existing request and emits nothing new (the open notification group stays as is). An ask while a refused row is unexpired answers 409 `join_request_refused`. Cancel deletes the request and the admins' open notification rows for it (new store method `delete_groups`), so a cancelled request leaves nothing to act on. No other rate limit: the remaining loop (cancel, ask again) is one person badging one team's admins, visible in the audit log, and an admin can switch the mode off.
6. **Recipients: current `team_admin` holders, filtered by `can_administer_members`.** The service lists the team's `team_admin` users and calls `notify` with `team_id` set and type `team.join_requested`, whose `ACTION_PERMISSION` is `CAN_ADMINISTER_MEMBERS`; slice 1's send-time filter, member removal, role loss (`forget_lost_access`) and team deletion then apply unchanged. Group `join_request:<request_id>`. Payload: `team_id`, `team_name`, `request_id`, `requester_id`, `requester_name`, `message`.
7. **Decision endpoints are the buttons' targets.** `POST /teams/{team_id}/join-requests/{request_id}/accept` and `/refuse`, gated by `can_administer_members` (re-checked server-side, never trusting the tile). Accept grants `team_member` through `_add_team_member_relation` (a no-op if the person became a member meanwhile), deletes the row and resolves the group with outcome `accepted`; refuse sets `status = refused`, `decided_*`, and resolves with `refused`. The deciding admin's row disappears; the others show "Handled by <name>". A decision on a request that is gone (decided, cancelled, expired, requester deleted) answers 404 `join_request_not_found`; the tile then deletes its notification and the list refetches.
8. **Mode changes do not touch pending requests.** Only creation checks `joining_mode == on_request`. Requests already pending when an admin leaves the mode (or makes the team private) stay decidable and cancellable, then expire. Accepting needs nothing the admin could not already do through Add members.
9. **Answer to the requester: type `team.join_request_answered`, no `team_id`, no permission.** `ACTION_PERMISSION` becomes `TeamPermission | None`; `None` is allowed only for types emitted without `team_id`, and `forget_lost_access` skips it. Payload: `team_id`, `team_name`, `outcome` (`accepted` | `refused`); it never names the deciding admin. Group `join_request_outcome:<request_id>`. Accepted: tile link and button "Open the team" to `/team/<team_id>/agents`; refused: no link, no button. Its rows survive the team's deletion (no `team_id`) and expire normally.
10. **Admin list: a "Pending requests" section at the top of the Members tab**, rendered only for `can_administer_members` holders and only while `GET /teams/{team_id}/join-requests` returns rows: name, message, date, Accept and Refuse calling the same endpoints. It covers an admin promoted after the request was sent (notifications are addressed at send time). The notification stays the main surface.
11. **Audit.** `team.join_request.created`, `.cancelled`, `.accepted`, `.refused` through `emit_audit_log` with `actor_uid`, `team_id`, `request_id` (and `requester_uid` on decisions); never the message text. Notification counters are slice 1's.
12. **Platform access.** Every new route sits behind the same authenticated platform-access gate as `POST /teams/{team_id}/join`, so a requester is admitted when asking; accept adds no admission source beyond what Add members already does. Implementation confirms the gate (task 3.1) rather than adding a second check.
13. **Cleanup.** `delete_team` deletes the team's requests (its notification rows already go by `team_id`); `delete_user` deletes the user's requests and the admins' open rows for them (`delete_groups`).

## Risks / Trade-offs

- [A promoted admin misses older requests in the bell] → the Members section lists them.
- [Cancel and ask again re-badges admins] → accepted (decision 5); revisit with a cooldown if it happens.
- [The requester's answer is lost if emission fails] → best effort as in slice 1; the card's state (`mine`) still shows the truth: the team appears under "Your teams" once accepted, "Request declined" once refused.
- [Three-way ButtonGroup on narrow screens] → checked in the live check; the group already wraps at small widths.

## Migration Plan

One linear Alembic revision whose `down_revision` is `fe166447f3d5` (slice 1's revision, the branch head; re-parent if `swift` moves, never `alembic merge`): create `team_join_requests` with its unique constraint and indexes. No existing row changes and no backfill: every team keeps its mode. Downgrade drops the table; a team left on `on_request` would then fail the older enum, so the downgrade also rewrites `on_request` to `invite_only`. The PR's migration note gains the second revision; impact stays minor.

## Open Questions

1. **Optional message with the request?** Recommendation: yes, optional, at most 280 characters, shown to admins only (tile body and Members section). Dropping it removes one field and one column.
2. **Re-asking after a refusal.** Recommendation: blocked until the request's 30-day expiry (decision 5). The alternative, re-asking at once, makes a refusal meaningless.
3. **Pending requests when the team leaves `on_request`.** Recommendation: keep them decidable until they expire (decision 8, no extra code). The alternative refuses them all automatically and notifies each requester.
4. **"Pending requests" section in the Members tab.** Recommendation: keep it (decision 10, one read route and one section). Without it, an admin promoted after a request never sees it.
