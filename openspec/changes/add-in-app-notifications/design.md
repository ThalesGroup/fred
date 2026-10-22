## Context

Full rationale, catalogue and alternatives: `docs/swift/rfc/NOTIFICATIONS-RFC.md`. This design covers slice 1 only.

Existing pieces this builds on:

- Feature layout and per-user "seen" precedent: `control_plane_backend/announcements/` and `models/announcement_models.py`.
- Periodic sweep: Temporal `LifecycleManagerWorkflow` (`scheduler/temporal/workflow.py`), wiki-proposal expiry as the template (`scheduler/lifecycle_runner.py`).
- Marketplace: `agent_marketplace/service.py` (`publish_agent`, `unpublish_agent`, `_state_view` computes Modified), `agent_marketplace/store.py` (`save_publication`, `remove_published_entries`), `product/service.py` (`update_agent_instance`).
- Frontend: `rework/components/shared/layouts/Sidebar/MainNavBar/MainNavBar.tsx`, `atoms/IconButton` (`badgeCount`), `molecules/UserProfile` (rail-anchored popover pattern), `molecules/MenuPopover`, `core/hooks/crossSessionRefresh.ts`.

## Goals / Non-Goals

**Goals:** a store and API general enough for slices 2 and 3 (actionable, multi-recipient, handled state) without changing them; a badge that updates within about 15 s; two marketplace types.

**Non-Goals:** other channels, preferences, toasts, a per-user stream, a service-to-service ingest route, join and boost requests.

## Decisions

1. **One row per recipient, text not stored.** `type` + `payload` render through i18n; a display snapshot (agent name, team name, actor name) is stored in the payload because names change and the subject may be gone.
2. **Type registry on both sides.** Backend: a `NotificationType` enum and a payload model per type (validated at `notify`). Frontend: a map type → icon, category, i18n keys, link builder, buttons. Category and buttons are not stored.
3. **Deduplication by group key.** Unique partial index `(recipient_id, group_key) WHERE handled_at IS NULL`; `notify` upserts: an open row gets its payload replaced, `seen_at`/`read_at` untouched, so a repeat never re-badges. After a group is resolved, a new emission creates a new row.
4. **`resolve(group_key, actor_uid, outcome)`** deletes the actor's own open row and sets `handled_at/by/outcome` on the others. A handled row keeps its `expires_at`.
5. **Best-effort emission after commit.** `notify` runs in its own transaction after the domain commit; failures log a warning with ids only and are counted. A lost notification is acceptable; a failed publish because of a notification is not.
6. **Delivery: polling `GET /notifications/summary` every 15 s while visible**, plus refetch on focus/visibility and invalidation after the user's own notification actions. The list is fetched when the popover opens. No held-open connection (the browser's ~6 per origin are already contested).
7. **"Seen" uses a cursor.** `POST /notifications/seen` takes the newest id the popover listed and marks rows created at or before it, so a notification arriving while the popover is open still badges.
8. **Pagination by `(created_at, id)` cursor**, page size 50.
9. **Expiry**: `expires_at = created_at + 30 days`, filtered on every read; the lifecycle step deletes expired rows in batches of 1000 until none remain or a 30 s budget is spent.
10. **Marketplace recipients from `published_by`.** Nullable column, set by `save_publication` on publish and republish. `agent.republish_needed` is emitted by `update_agent_instance` when the save changed the agent, the entry is Published, and `published_by` is set and differs from the editor; group `agent_republish:<entry_id>`. Republish or removal of the entry calls `resolve` on that group (the actor's row disappears, otherwise "Handled by"). `agent.marketplace_removed` is emitted wherever the entry enters the Removed state, unless the actor is the publisher; group `agent_removed:<entry_id>:<removed_at>`; it carries the reason code and the platform admin's message if any.
12. **A notification reaches only who can act on it now.** Each type declares in `ACTION_PERMISSION` (`notifications/schemas.py`) the team permission needed to act on it; both slice-1 types require `can_update_agents`, since only an agent editor can republish. `notify_many` drops a draft whose recipient lacks that permission on the draft's team (one ReBAC check per distinct recipient, team and permission). Rights lost after sending are handled by deletion, not a read-time check, so the 15 s summary stays one indexed query: `remove_team_member` deletes the member's rows for the team, `delete_team` the team's rows, and every role loss (`revoke_team_member_role`, an admin removed in `edit_team_registry`, a charter demotion) calls `forget_lost_access`, which deletes the open rows of each type whose permission the user no longer holds. A draft without `team_id` is never filtered, so a later type addressed to a non-member (a join request's answer) leaves `team_id` empty. A permission changed outside these paths (a direct OpenFGA edit) leaves its rows until they expire; acting on one still goes through the domain endpoint's own check.
11. **Navigation-only buttons in slice 1.** Both types offer "Open the agent", routing to the team's Agents page with `?agent=<agent_instance_id>`, which opens that agent's edit form for an editor; the existing republish flow there does the rest. Domain-endpoint buttons are part of the framework and first used in slice 2.

## Backend implementation notes (divergences to confirm)

- `handled_by_name` column: a display snapshot, like the payload's names, so "Handled by <name>" needs no user lookup. Removals by deactivation, suspension or deletion go through the agent store, which knows no name: those rows show only `handled_outcome = removed`.
- Index shapes: the list index is ascending `(recipient_id, created_at, id)` (a backward scan serves DESC), and the unique open-group index is ordered `(group_key, recipient_id)` so `resolve` uses it too.
- The view is a union discriminated by `type` with one payload model per type, so the generated client types each payload instead of a hand-written frontend type. A row of a type this version does not know is skipped by the list.
- `POST /notifications/seen` answers the new `NotificationSummary`; `before` is an opaque cursor (`next_cursor`), not a notification id.
- `notification_type` is not in `PROMETHEUS_ALLOWED_LABELS`: per-type counts reach OpenSearch only. Adding the label is an owner decision.

## Frontend implementation notes (divergences to confirm)

- The badge reads "99+" above 99 (`IconButton badgeMax`, default 999 for other callers).
- The bell, its popover, the polling hook and the type registry live in `rework/features/notifications/` (they consume RTK hooks); only `NotificationTile` is a shared molecule, props only. `MainNavBar` renders `NotificationsEntry` after its entries.
- "Open the agent" leads to the team's Agents page with `?agent=<agent_instance_id>` (no per-agent route exists, so the page opens that agent's edit form for an editor and drops the param; a member, or an agent gone since, just lands on the page). The tile click follows the same link, so in slice 1 the button repeats the tile click; it is there for the button framework (`navigate` or `call` a domain endpoint, the latter unused until slice 2).
- Acting on a tile deletes it (owner decision, 2026-10-22): a tile click or a `navigate` button deletes the row then navigates; a `call` button deletes nothing itself, since the domain endpoint's `resolve` already deletes the actor's row on success and a failure must keep the tile. The popover no longer calls `read`; the route stays, unused by the frontend. The close button is always visible, beside the unread dot.
- Cache tags: `seen` refreshes the badge only; `read` (which also marks seen), delete and clear refresh both.
- A tab opened in the background sends no summary request until it is first shown.
- A handled row without `handled_by_name` (removal by deactivation, suspension, deletion) reads "Resolved: the agent left the marketplace".
- Focus goes to the popover title on opening and back to the bell on Escape or the back arrow; the narrow-screen sheet does not trap focus.
- Tests use the repository's `react-dom` + `act` pattern; `@testing-library` is not a dependency.

## Risks / Trade-offs

- [Polling cost at scale] → one indexed count per visible tab every 15 s, nothing when hidden; measured in verification with the existing mock load tooling if needed.
- [Up to 15 s latency vs. "immediately"] → accepted by the owner; a stream can replace polling later behind the same summary contract.
- [Bulk removal fans out] (a platform switch turning publication off for many teams) → one row per entry for its publisher, emitted in one batched insert.
- [Legacy entries have no publisher] → they notify nobody until the next republish; stated in the Help Center.

## Migration Plan

One linear Alembic revision on the control-plane head current at implementation time (re-parent if `swift` moves; never `alembic merge`): create `notifications` with its indexes, add nullable `agent_marketplace_entries.published_by`. Downgrade drops both. Minor version; migration note states no operator action.

## Open Questions

None. The owner closed the RFC's three open questions on 2026-10-22: 15 s polling is the "live" badge (decision 6); slice 2 brings join requests through a new opt-in team access mode, "on request", reversing §29's removal of `request_only`; slice 3 sends boost requests to the admins of the requester's teams, with no platform admin fallback since every team has an admin.
