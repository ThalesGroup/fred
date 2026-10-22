# RFC — In-app notifications

**Status:** Owner decisions recorded 2026-10-22; no open question left.
GitHub issue #3232. Slice 1 is scoped as the OpenSpec change
`add-in-app-notifications`, slice 2 as `add-team-join-requests` (same
branch and PR); slice 3 gets its own change.

## 1. Problem

Fred has no way to tell one user that something needs them. Every
person-to-person flow works around that gap:

- `request_only` team joining was dropped (`FRED-TEAM-CONFIG-RFC.md` §5.1.1,
  `CONTROL-PLANE-PRODUCT-CONTRACT.md` §29) because no notification system
  existed to route the request to team admins.
- An editor who changes a published agent is offered to republish it, but
  only in their own session (`RepublishProposalDialog`). If they choose
  "Ignore", the agent stays Modified and nobody else is told.
- When a platform admin or an automatic rule removes a marketplace entry, the
  publisher learns it only if they happen to open the team's Agents page.
- Quota boosts (#3223) are granted by admins, with no way for a user to ask.

What exists today, none of it per-user targeted:

- Announcements and patch notes (`control_plane_backend/announcements/`):
  broadcast to every user, polled every 60 s, with a one-row-per-user
  "seen" high-water mark (`platform_announcement_seen`).
- Task acknowledgement (`fred_core/tasks/`): "needs attention" for the
  tasks a user started (imports, evaluations). It stays the home for task
  outcomes; notifications do not duplicate it.

## 2. Decided (owner, issue #3232)

1. In-app only for v1. The model must allow other channels later.
2. The badge counts unseen notifications; opening the popover resets it.
   Each tile keeps an unread style until clicked.
3. A notification arriving while the user is in the app updates the badge
   without reload. No toast in v1.
4. Expiry after 30 days. An actionable notification disappears for the
   recipient who acted on it, and shows "handled" to the other recipients.
5. No per-category preferences in v1.
6. Quota boost requests are a notification type of this work item, wired
   once the #3223 boost API exists.
7. Small starting set: first what asks the user to act, then what answers a
   request the user made; pure information last.
8. 15 s polling of the badge counts as "without reload" for decision 3
   (§3.5); no stream.
9. The badge reads "99+" above 99.
10. A notification reaches only people who can currently act on what it
    asks. Each type declares the permission needed to act on it, on the
    notification's team (both marketplace types: `can_update_agents`; join
    requests: `can_administer_members`; boost requests: the team admin
    right). It is checked per recipient at send time, and a loss of that
    right (role change, leaving the team, team deletion) deletes the
    recipient's open notifications of that type.
11. Join requests come through a new opt-in team access mode, "on request",
    next to `open` and `invite_only` (slice 2). Admins who keep either
    existing mode receive no requests, as today.
12. A quota boost request goes to the admins of the requester's teams
    (slice 3). Every team has at least one admin, so there is no platform
    admin fallback.

## 3. Design

### 3.1 Data model

One control-plane table, `notifications`, one row per recipient:

| Column | Meaning |
|---|---|
| `id` | UUID |
| `recipient_id` | user uid; every read and write is scoped to it |
| `type` | registered type, e.g. `agent.republish_needed` |
| `team_id` | nullable; the team the notification is about (cleanup, links) |
| `group_key` | shared by every row about the same subject, e.g. `join_request:<id>`; used to resolve a group and to deduplicate |
| `payload` | JSON: ids plus a display snapshot (agent name, team name, actor name) taken at creation |
| `created_at`, `expires_at` | `expires_at = created_at + 30 days` |
| `seen_at` | set when the popover opens; badge = rows with `seen_at IS NULL` |
| `read_at` | set when the tile is clicked |
| `handled_at`, `handled_by`, `handled_outcome` | set when the group is resolved |

- **Text is not stored.** The frontend renders title, body and buttons from
  `type` + `payload` with i18n keys, so a notification follows the viewer's
  locale and a wording fix applies to existing rows.
- **Category and actions are not stored.** A type registry (backend enum +
  frontend map) gives each type its category (`action_required`, `response`,
  `information`), its buttons and its link.
- **Deduplication:** a unique partial index on `(recipient_id, group_key)`
  where `handled_at IS NULL`. Re-emitting an open subject updates its payload
  and leaves `seen_at`/`read_at` as they are, so it never re-badges.
- **Channels:** the emitter API takes no channel. When email comes, a
  per-type channel list and a delivery table are added behind the same
  API. Nothing is built for it in v1.
- Indexes: `(recipient_id, created_at DESC)` for the list, a partial index on
  `recipient_id` where `seen_at IS NULL` for the badge, `expires_at` for the
  sweep.

### 3.2 Emitting

A single control-plane service owns the table:

```python
await notifications.notify(recipients, type, payload, group_key, team_id)
await notifications.resolve(group_key, actor_uid, outcome)  # handled for all
```

- Domain services call it in-process after their own commit. Emission is
  best effort: a failure logs a warning and never fails the domain action.
- `resolve` deletes the actor's own row and marks every other open row of
  the group handled (decision 4).
- Every v1-v3 trigger lives in control-plane. Other services (fred-agents,
  knowledge-flow) get a service-only ingest route, authenticated by the
  existing M2M client-credentials token, only when their first notification
  type is scoped. It is not built before.

### 3.3 API (control-plane, caller-scoped)

| Route | Effect |
|---|---|
| `GET /notifications/summary` | `{unseen_count}`; one indexed count |
| `GET /notifications?limit=50&before=<cursor>` | newest first, expired rows excluded |
| `POST /notifications/seen` | marks every row up to the newest listed id as seen |
| `POST /notifications/{id}/read` | marks one row read |
| `DELETE /notifications/{id}` | deletes one row |
| `DELETE /notifications` | clear all |

All routes are `authenticated_user` in `authz-endpoint-matrix.yaml`; a row of
another user answers 404. No route creates a notification.

### 3.4 Actions

A button calls the **domain endpoint** that already authorizes the action
(publish an agent, approve a join request, grant a boost), never a generic
"execute notification action" route. The domain service then calls
`resolve(group_key, …)`. A button that only navigates (open the agent) uses a
route built from the payload and marks the tile read. Domain rules stay in
one place, and an action from the notification behaves exactly like the same
action taken from its page.

### 3.5 Delivery to the browser

**Decided: light polling of `GET /notifications/summary` every 15 s
while the tab is visible**, paused when hidden, refetched on focus and on
visibility change, and invalidated right after the user's own actions. The
list is fetched only when the popover opens.

- No held-open connection: the browser's ~6 connections per origin are
  already contested (import SSE exhaustion, `useTaskPolling.ts`).
- A per-user SSE stream would need a fan-out the code does not have:
  `PostgresEventBus` opens one asyncpg connection plus `LISTEN` per
  subscriber, which does not scale to one stream per open tab.
- Cost: one indexed count per visible tab every 15 s, safe across
  replicas, no state in memory.

### 3.6 Retention

- Reads filter `expires_at > now()`, so correctness never waits for a sweep.
- The existing Temporal `LifecycleManagerWorkflow` (every 10 min) gets a
  `run_notification_expiry_once` step deleting expired rows in bounded
  batches, like the wiki-proposal expiry. In memory mode it runs from
  `POST /lifecycle/run-once`.
- Deleting a user deletes their rows (`users/api.py`, next to
  `delete_seen_for_user`). Deleting a team deletes the rows carrying its
  `team_id`.

### 3.7 Authorization, audit, observability

- A user only reads and changes their own rows (`recipient_id = user.uid`).
- Recipients are computed server-side by the domain service, from ReBAC
  (team admins) or stored ownership (`published_by`), never from the client.
- The domain action is audited by its own endpoint, as today. Reading,
  deleting and clearing are the user's own data and are not audited.
- One counter `notifications_created_total{type}`; logs carry ids, never
  payload text.

### 3.8 Frontend

- `MainNavBar` gains a bell entry with `IconButton badgeCount` (the count is
  repeated in the `aria-label`, the badge is `aria-hidden`).
- The popover follows the `UserProfile` pattern: anchored to the rail,
  opening over the nav panel, closed by outside click and Escape. Header with
  "Clear all", a list of tiles, an empty state.
- A `NotificationTile` molecule: icon by category, title, body, relative
  time, unread style, delete button, the type's buttons, and a "Handled by
  <name>" line instead of buttons once handled.

## 4. Catalogue

Legend: AR = action required, R = answer to your request, I = information.
"Exists" = the trigger is in the code today.

| # | Notification | Trigger | Recipients | Cat. | Buttons | Group / handled | Exists |
|---|---|---|---|---|---|---|---|
| 1 | Published agent changed by another editor: update the marketplace version | `update_agent_instance` (`product/service.py`) when the save makes the entry Modified (`agent_marketplace/service.py` `_state_view`) | the entry's `published_by`, if not the editor | AR | Open the agent | `agent_republish:<entry>`; resolved by republish or removal | Yes; needs `published_by` on the entry |
| 2 | Your agent was removed from the marketplace (by a platform admin or automatically) | wherever the entry enters the Removed state (`unpublish_agent` with a platform reason, `remove_published_entries`), unless the publisher caused it | `published_by` | I | Open the agent | `agent_removed:<entry>`; none | Yes; needs `published_by` |
| 3 | X asks to join your team | new join-request endpoint | team admins (`CAN_ADMINISTER_MEMBERS`) | AR | Accept, Refuse | `join_request:<id>`; resolved by the first admin decision | No: the "on request" mode and a request record are new |
| 4 | Your request to join T was accepted / refused | decision on 3 | requester | R | Open the team (accepted) | `join_request_outcome:<id>` | No (with 3) |
| 5 | X asks for a quota boost | "Request a boost" in the quota tooltip (#3223 slice c) | admins of the requester's teams (decision 12) | AR | Grant +20%, Decline | `boost_request:<user>:<week>`; resolved by grant/decline | No: after #3223 |
| 6 | Your boost request was granted / declined | decision on 5 | requester | R | none | `boost_outcome:<id>` | No: after #3223 |
| 7 | Your weekly quota is at 80% / exhausted | #3223 spend counters | the user | I | none | one per window | No: after #3223; the composer indicator already warns in context |
| 8 | An agent finished a turn while you were away | turn end | the user | I | Open the conversation | per session | No: a turn ends with its browser connection (`agent_app.py` "a closed connection ends the run") |
| 9 | Your agent is waiting for your answer (HITL) | runtime `AWAITING_HUMAN` | the user | AR | Open the conversation | per interrupt | No: control-plane is never told |
| 10 | Someone joined your team through the invite link | `platform_access/service.py` `enroll` | team admins | I | none | per team per day | Yes; low value |
| 11 | A new UI theme is available | admin theme settings | everyone | I | Open settings | per theme | Partly; broadcast belongs to patch notes |

**v1 set:** 1 and 2 (slice 1), 3 and 4 (slice 2), 5 and 6 (slice 3, after
#3223). 7 is decided after slice 3 lands. 8 and 9 wait for turns that can
outlive the connection. 10 and 11 are dropped: 11 is product news and already
has the patch-note channel.

Notes on 1 and 2:

- Today `agent_marketplace_entries` does not record who published. Slice 1
  adds a nullable `published_by`, written on every publish and republish.
  Entries published before the upgrade have none and notify nobody until
  their next republish (no backfill; the audit log is not a data source).
- The editor who saves already gets the republish dialog in their session;
  the notification only goes to a different publisher.

## 5. Open questions

None. The three questions this section held are closed by the owner
(2026-10-22):

1. Latency: 15 s polling (decision 8).
2. Join requests: a new opt-in `joining_mode` value, "on request"
   (decision 11). This reverses the removal of `request_only` in §29 of
   `CONTROL-PLANE-PRODUCT-CONTRACT.md`; the slice 2 change adds a dated
   contract entry for it, fixes the wire value, and revisits the importer's
   mapping of legacy `request_only` to `invite_only`.
3. Boost recipients: the admins of every non-personal team the requester
   belongs to (decision 12). The first grant or decline resolves the group
   for all, matching #3223's "once per user per week across all teams".

## 6. Slices

1. **Foundation** (OpenSpec `add-in-app-notifications`): table and Alembic
   revision, service, caller API, OpenAPI and client regeneration, bell,
   badge, popover, tile, clear all / delete, seen/read, 15 s badge polling,
   action-button framework, expiry step, `published_by`, types 1 and 2,
   Help Center fr+en, migration note (minor).
2. **Team join requests** (OpenSpec `add-team-join-requests`): the opt-in
   `on_request` access mode for public teams, join-request record and
   endpoints, "Ask to join" on the team card, a Members-tab pending list,
   types 3 and 4.
3. **Quota boost requests:** after #3223 slices (b) and (c); types 5 and 6.

Each slice is its own OpenSpec change. Once slice 3 is scoped, this RFC has
nothing left open and folds into the archived specs.

## 7. Alternatives considered

- **Per-user SSE stream.** Instant, but one held connection per tab and a
  `LISTEN` connection per subscriber in the current bus. Rejected for v1.
- **Reuse the announcements tables.** Announcements are broadcast with one
  high-water mark per user; per-recipient rows, actions and handled state
  would bend that model past recognition.
- **Reuse task acknowledgement.** Tasks are work the user started, owned by
  the backend that runs it; notifications are addressed by someone else.
- **Store rendered text.** Freezes the locale at creation and blocks wording
  fixes. Rejected; ids plus a display snapshot instead.
- **Generic action endpoint** (`POST /notifications/{id}/actions/{name}`).
  Duplicates domain authorization in a second place. Rejected.
- **Outbox and worker for emission.** Durable, but every v1 trigger is in
  control-plane and best effort is acceptable for a notification.
