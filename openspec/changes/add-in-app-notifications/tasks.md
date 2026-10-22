## 1. Control-plane model and migration

- [x] 1.1 Add `models/notification_models.py` (`NotificationRow`: `id`, `recipient_id`, `type`, `team_id`, `group_key`, `payload` JSON, `created_at`, `expires_at`, `seen_at`, `handled_at`, `handled_by_name`, `handled_outcome`) with indexes `(recipient_id, created_at DESC, id)`, partial `recipient_id WHERE seen_at IS NULL`, `expires_at`, and the unique partial `(recipient_id, group_key) WHERE handled_at IS NULL`; register it in `models/table_ownership.py`; verify `make test` in `apps/control-plane-backend`.
  - Done: `models/notification_models.py`; list index ascending `(recipient_id, created_at, id)` (backward scan serves DESC), unique open-group index ordered `(group_key, recipient_id)` so `resolve` uses it; `handled_by_name` is a display snapshot for "Handled by" (no `handled_by` uid, no `read_at`). `make test` green.
- [x] 1.2 Add nullable `published_by` to `AgentMarketplaceEntryRow` (`models/agent_marketplace_models.py`); verify existing marketplace tests pass.
  - Done: `AgentMarketplaceEntryRow.published_by`; `tests/test_agent_marketplace.py` green.
- [x] 1.3 Create one Alembic revision creating `notifications` and adding `agent_marketplace_entries.published_by`, `down_revision` = the current single head (re-parent if `swift` moved; never `alembic merge`), downgrade dropping both; verify `make db-check-heads` (one head) and `make db-check-sqlite` pass, then `make db-upgrade`, `make db-downgrade`, `make db-upgrade` against a real Postgres.
  - Done: squashed with slice 2 into revision `83b81adf7450` (down `c9acb7dd3ad0`). `make db-check-heads` (one head) and `make db-check-sqlite` passed before the squash; the real Postgres round trip (2026-10-22, scratch copy `fred_notif`) ran on the pre-squash revisions. Re-verification of the squashed revision: `verification.md`.

## 2. Control-plane service

- [x] 2.1 Add `notifications/schemas.py`: `NotificationType` enum (`agent.republish_needed`, `agent.marketplace_removed`), one payload model per type, `NotificationView`, `NotificationPage`, `NotificationSummary`; verify payload validation tests (unknown type, missing field).
  - Done: `notifications/schemas.py`; the view is a union discriminated by `type`, one payload model per type, so the generated client types each payload. `tests/test_notifications.py`.
- [x] 2.2 Add `notifications/store.py` (async SQLAlchemy, `announcements/store.py` pattern): upsert by `(recipient_id, group_key)` keeping `seen_at`, batched insert for many recipients, unseen count, cursor page, mark seen up to a cursor, delete one, delete all, resolve group, delete expired in batches, delete by user, delete by team; every caller-facing query filters `recipient_id` and `expires_at > now()`; verify store tests for each, including that a repeat emission does not reset `seen_at` and that a resolved group accepts a new row.
  - Done: `notifications/store.py`; the cursor is opaque `<created_at µs>.<id>`; an expired open row is replaced by a new emission. `tests/test_notification_store.py` (13 tests).
- [x] 2.3 Add `notifications/service.py`: `notify(drafts)` and `resolve(group_keys, actor_uid, actor_name, outcome)` (actor's row deleted, others handled), both best effort and returning nothing (warning with ids only, `notifications_created_total{type}` and a failure counter); verify tests: a store exception does not raise, the actor's row disappears, other recipients see `handled_by_name`.
  - Done: `notifications/service.py`; counters `notifications.created_total` (dim `notification_type`, not a Prometheus label, so OpenSearch only) and `notifications.emit_failed_total` (`status`). `tests/test_notifications.py`.
- [x] 2.4 Wire the store and service in `app/context.py` and `product/dependencies.py`; verify the app starts in tests.
  - Done: container `get_notification_service`/`get_notification_store`; optional `get_notification_service` on product and team deps; the agent store receives the service.

## 3. Control-plane API

- [x] 3.1 Add `notifications/api.py`: `GET /notifications/summary`, `GET /notifications` (`limit` ≤ 50, `before` cursor), `POST /notifications/seen` (`up_to` id), `DELETE /notifications/{id}`, `DELETE /notifications`; mount in `main.py`; another user's id answers 404; verify API tests for each route including the 404 and the expired-row exclusion.
  - Done: `notifications/api.py` mounted in `main.py`; `seen` answers `NotificationSummary`, delete/clear 204; route, 404, 422 and 401 tests in `tests/test_notifications.py`.
- [x] 3.2 Add the five routes to `docs/swift/platform/authz-endpoint-matrix.yaml` as `authenticated_user`; verify the authz matrix test passes.
  - Done: five `authenticated` entries (`pending_review`); `tests/test_authz_endpoint_matrix.py` green.
- [x] 3.3 Delete a user's notifications in `delete_user` (`users/api.py`, next to `delete_seen_for_user`) and a team's in team deletion; verify a test for each.
  - Done: `delete_user` (`tests/test_user_delete_route.py` call order) and `delete_team`, before the team row (`test_team_deletion_deletes_the_teams_notifications`).

- [x] 3.4 Send a team's notifications only to its current members and delete a member's notifications about a team they leave or are removed from; verify tests for both.
  - Done: `NotificationService(get_rebac=...)` filters drafts (by the type's permission since 3.5); `remove_team_member` calls `NotificationService.delete_for_member`. Tests: `test_a_publisher_who_left_the_team_is_told_nothing`, `test_leaving_a_team_removes_only_that_members_rows_about_it`, `test_remove_team_member_self_removal_skips_permission_check`.

- [x] 3.5 Send each notification only to recipients holding the permission its type declares (`can_update_agents` for both marketplace types) and delete a recipient's open rows of a type when they lose that permission through a role change; verify tests.
  - Done: `PERMISSION` on each payload class in `schemas.py`, checked by `NotificationService._allowed_recipients`; `forget_lost_access` called from the membership hook `_on_team_access_changed`, run after every grant or revoke; `store.delete_for_member(types=...)`. Tests: `test_every_type_declares_the_permission_to_act_on_it`, `test_a_team_notification_skips_who_cannot_act_on_it`, `test_losing_the_right_to_act_drops_those_notifications`, `test_a_lost_right_removes_only_the_types_it_covered`, `test_a_publisher_who_can_no_longer_edit_the_agents_is_told_nothing`, `test_revoke_team_member_role_drops_notifications_the_member_cannot_act_on`.

## 4. Expiry

- [x] 4.1 Add `run_notification_expiry_once` to `scheduler/lifecycle_runner.py` (one bounded delete of 1000 rows per tick), an activity in `scheduler/temporal/activities.py`, a step in `LifecycleManagerWorkflow` and in the memory runner (`POST /lifecycle/run-once`); verify tests: rows past `expires_at` deleted, others kept, at most one batch per tick.
  - Done: `run_notification_expiry_once`, activity `expire_notifications_and_join_requests` (`NOTIFICATION_EXPIRY_BATCH_SIZE`), registered in the worker; `LifecycleManagerResult.notifications.deleted`. `tests/test_memory_lifecycle_runner.py`.

## 5. Marketplace triggers

- [x] 5.1 Write `published_by = user.uid` in `save_publication` on publish and republish (`agent_marketplace/store.py`, from `publish_agent`); verify a test for both.
  - Done: `save_publication(published_by=...)`; `test_publish_and_republish_record_the_publisher`.
- [x] 5.2 In `update_agent_instance` (`product/service.py`), after the store update and commit, emit `agent.republish_needed` when the save changed the agent, the entry is Published, and `published_by` is set and differs from the editor (group `agent.republish_needed:<entry_id>`, payload: team, agent, entry ids and names, editor name); verify tests: emitted for another editor, not for the publisher, not for a no-op save, not for a legacy entry, a second save does not re-badge.
  - Done: `agent_marketplace/notifications.py::notify_republish_needed`, called from `update_agent_instance`; tests for another editor, publisher, no-op, legacy entry, second save, failing store.
- [x] 5.3 Resolve `agent.republish_needed:<entry_id>` on republish and on removal; verify the publisher's own republish deletes their row and another editor's republish marks it handled.
  - Done: `resolve_republished` after `save_publication`; every removal resolves the group with outcome `removed` (deactivation, suspension and deletion paths carry no actor name). `test_republishing_resolves_the_request`.
- [x] 5.4 Emit `agent.marketplace_removed` wherever an entry enters the Removed state (`unpublish_agent` with a platform reason, `remove_published_entries` callers) unless the actor is the publisher, batched for bulk removals (group `agent.marketplace_removed:<entry_id>:<removed_at>`, payload with the reason code and the admin message); verify tests: platform-admin removal, automatic removal (team made private), removal by a team editor emits nothing, bulk switch-off emits one row per entry in one insert.
  - Done: `notify_unpublished` at every `emit_unpublished` site: unpublish, switch-off (default and team), team made private, deactivation, suspension, deletion (resolve only). Tests: platform admin, team private, team removal, bulk switch-off (one insert of 2), deactivation by another editor.

## 6. API client

- [x] 6.1 Regenerate without wiping a running Vite: `cd apps/control-plane-backend && make generate-openapi`, then `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`; verify `controlPlaneOpenApi.ts` gains the routes and nothing is hand-edited.
  - Done: `make generate-openapi`, then `make update-control-plane-api` after a real `npm ci` in the worktree; only additions in `controlPlaneOpenApi.ts`; `npx tsc --noEmit` and prettier green.
- [x] 6.2 In `controlPlaneApiEnhancements.ts`: a `ControlPlaneNotification` tag, summary and list providing it, every mutation invalidating it, friendly aliases (`useNotificationSummaryQuery`, `useNotificationsQuery`, `useMarkNotificationsSeenMutation`, `useDeleteNotificationMutation`, `useClearNotificationsMutation`); verify `npx tsc --noEmit`.
  - Done: tag `ControlPlaneNotification` (`SUMMARY` on the summary, `LIST` on the list); `seen` invalidates `SUMMARY` only, delete and clear the whole tag; the five aliases. `npx tsc --noEmit` green.

## 7. Frontend

- [x] 7.1 Add a notification type registry under `rework/features/notifications/` (type → icon, category, i18n keys, link builder, buttons; unknown types render a generic tile); verify a vitest for both v1 types and an unknown type.
  - Done: `rework/features/notifications/notificationTypes.ts`, typed per `type` from the generated union; `renderNotification` gives icon, category, title, body, link, buttons (`navigate` or `call` a domain endpoint) and the handled label. `notificationTypes.test.ts` (9 tests: both types, reason fallback, locale, no team name, handled by name, handled by removal, unknown type, no missing key in fr/en).
- [x] 7.2 Add the `NotificationTile` molecule: category icon, title, body, relative time, no read/unread distinction (a click follows the link), delete IconButton (`size="medium"`, `color="on-surface-retreat"`), the type's buttons, "Handled by <name>" instead of buttons once handled; design tokens only, `outline-*` borders, full `surface-` names; verify vitest for open, handled and delete.
  - Done: `shared/molecules/NotificationTile/` (props only; icon well per category, full body text (never truncated, owner decision), always-visible close button). `NotificationTile.test.tsx`.
- [x] 7.3 Add the `NotificationsPopover` following the `UserProfile` popover pattern (anchored to the rail, over the nav panel, outside click and Escape close it): header with "Clear all", tiles newest first, load more, empty state; opening it fetches the list and posts `seen` up to the newest listed id; verify vitest for open, seen call, clear all, empty state, Escape.
  - Done: `rework/features/notifications/NotificationsPopover.tsx` on `MenuPopover` (`role="dialog"`), `PageEmptyState` for the empty state, "Show more" by `next_cursor`, full-screen sheet with a back arrow at 600px and below; `seen` is posted once per opening, only from an answer fetched since the opening. Escape and outside click live in the bell entry (`NotificationsEntry.tsx`). `NotificationsPopover.test.tsx` (seen up_to newest, not from a stale cache, not when all seen, delete + navigate, delete, clear all, empty state, load more, focus on open).
- [x] 7.4 Add the bell entry to `MainNavBar.tsx` with `IconButton badgeCount` from `useNotificationSummaryQuery` polled every 15 s while the tab is visible (paused when hidden, refetched on focus and visibility change); the count goes into the `aria-label`; verify vitest for badge shown, hidden at 0, aria-label, no polling while hidden.
  - Badge cap: `IconButton badgeMax` (default 999), set to 99 on the bell; tests in `IconButton.test.tsx` and `NotificationsEntry.test.tsx`.
  - Done: `NotificationsEntry` rendered last in `MainNavBar.tsx`; `useNotificationSummary` polls every 15 s while visible, 0 while hidden, refetches on visibility return and on focus (`useRefetchOnWindowFocus`), and a tab opened hidden sends nothing until shown. `NotificationsEntry.test.tsx` (8 tests: badge, none at 0, aria-label, 15 s interval, hidden pause + catch-up, focus, background tab, Escape onto the bell, outside click).
- [x] 7.6 Dismiss a tile once its recipient acts on it (owner decision, 2026-10-22): always-visible close button "Dismiss notification" / "Ignorer la notification"; tile click and `navigate` buttons delete then navigate; `call` buttons leave the deletion to the endpoint's success; verify vitest.
  - Done: `NotificationTile` (`dismissLabel`/`onDismiss`, no hover-only rule), `NotificationsPopover`; `NotificationTile.test.tsx` (close button present without hover) and `NotificationsPopover.test.tsx` (click deletes + navigates, navigate action deletes + navigates, failed `call` keeps the tile, close deletes). Owner live check pending.
  - Pending decisions: no close button (`dismissible={false}`), a click follows the link without deleting, the close button returns once handled; "Clear all" keeps them (backend `delete_all`) and is disabled when only they are listed; buttons disabled while a call is in flight (`busy`); a 404 or 403 removes the tile silently. Tests: `NotificationsPopover.test.tsx` (one call per double click, pending tile follows without delete and has no close, clear all disabled), `NotificationTile.test.tsx` (busy), `notificationTypes.test.ts` (403/404, `isPendingDecision`), `tests/test_notification_store.py::test_clear_all_keeps_the_decisions_still_waiting`.
- [x] 7.5 Add fr + en strings (`rework.notifications.*`, `rework.mainNav.notifications`); verify `npx tsc --noEmit` and no missing-key warnings in touched tests.
  - Done: `rework.notifications.*`, `rework.mainNav.notifications`, `rework.mainNav.notificationsUnseen_{one,other}` in fr and en; removal reasons reuse `rework.agentMarketplace.removed.reasons.*`. Missing-key check in `notificationTypes.test.ts`.

## 8. Docs, Help Center and migration note

- [x] 8.1 Add `rework/features/helpCenter/content/{fr,en}/features/notifications.md` (what the bell shows, seen vs. handled, clear and delete, 30-day expiry, the two marketplace notifications, legacy entries without a publisher); verify `helpCenter/content.test.ts`.
  - Done: `content/{fr,en}/features/notifications.md` (order 47) plus a line in each `features/index.md` and two cross-links in each `agents.md`; `helpCenter` tests green (18).
- [x] 8.2 Add a dated numbered entry to `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (routes, caller scope, `published_by`, expiry); verify it follows the latest section's format.
  - Done: §69 of `CONTROL-PLANE-PRODUCT-CONTRACT.md`.
- [x] 8.3 Write `docs/swift/ops/migrations/add-in-app-notifications.md` from the template, impact `minor` (Alembic migration, no operator action); verify `make migration-check` from the repo root.
  - Done: `docs/swift/ops/migrations/3232-add-in-app-notifications.md`; `make migration-check`: "Migration notes valid: 1 new declaration(s)".
- [x] 8.4 Update `docs/swift/ux/COMPONENT-UX.md` for `NotificationTile`, `NotificationsPopover` and the bell entry.
  - Done: new section "Notifications: bell, `NotificationsPopover`, `NotificationTile`" and `NotificationsPopover` listed as a `MenuPopover` instance.
- [x] 8.5 Update `docs/swift/rfc/NOTIFICATIONS-RFC.md` status: slice 1 shipped, folded into the `notifications` spec.
  - Done: the RFC is trimmed to what is still open (slice 3 and catalogue items 7–9) and points to both OpenSpec changes and contract §69/§70.

## 10. Platform switch per notification type

- [x] 10.1 Add `DisabledNotificationTypeRow` (`disabled_notification_types`) to the single revision `83b81adf7450`; verify `alembic heads` shows one head and `alembic upgrade head` on the scratch database.
- [x] 10.2 `NotificationStore.disabled_types/disable_type/enable_type`; the list, the unseen count and Clear all skip disabled types (producers still store); `list_type_settings`/`set_type_enabled` gated by `can_manage_platform`, audit `platform.notification_type.updated`; verify `tests/test_notifications.py`.
- [x] 10.3 Routes `GET /admin/platform/notification-types` and `PUT /admin/platform/notification-types/{notification_type}`; `authz-endpoint-matrix.yaml`; §69 of `CONTROL-PLANE-PRODUCT-CONTRACT.md`; regenerate `controlPlaneOpenApi.ts`.
- [x] 10.4 Admin page `NotificationsPage` (`/admin/notifications`, AdminNavbar entry, `requires="admin"`): one row per listed type with name, description and `Switch`; fr+en `rework.notificationSettings.*` (page) and `rework.notifications.types.<key>.name`/`description` (per type); Help Center administration line fr+en; verify `NotificationsPage.test.tsx`.
- [x] 10.5 A failed `call` action (not 404/403) shows the error toast; verify `notificationTypes.test.ts` and `NotificationsPopover.test.tsx`.
- [x] 10.7 Turning a type off asks for confirmation (critical `ConfirmationDialog`, fr+en `rework.notificationSettings.turnOff.*`); turning it on does not; verify `NotificationsPage.test.tsx`.
  - Done: `NotificationsPage.test.tsx` (on saves at once, off asks then saves on confirm, failure toast).
- [x] 10.8 Performance review fixes: plain indexes on `notifications.team_id` and `group_key` in the revision and the model; `KPIMiddleware` skips `/notifications/summary`; verify `test_table_ownership.py`, `fred_core/tests/kpi/test_http_middleware.py`.
  - Done: both green; `alembic heads` one head (`83b81adf7450`).
- [ ] 10.6 Owner live check: turn `team.join_requested` off, ask to join an on_request team → no notification shown and existing ones hidden; the request is still in Members > Pending requests; turn it back on → the hidden notifications reappear.

## 11. Quality refactor (2026-10-22)

- [x] 11.1 Delete the read state: `POST /notifications/{id}/read`, `read_at` and the unread tile style; drop the write-only `handled_by` column.
- [x] 11.2 Declare each type's rules on its payload class (`TYPE`, `PERMISSION`, `DECISION`); one `notify(drafts)`; group keys `group_key(type, subject_id)`.
- [x] 11.3 fred-core `KPIMiddleware(skip_suffixes=...)`; control-plane passes `/notifications/summary`.
- [x] 11.4 Required notification service and join request store; one membership hook `_on_team_access_changed`; cleanups through `NotificationService.delete_for_team`/`delete_for_member`/`delete_for_user`.
- [x] 11.5 Expiry: one bounded delete per tick (`expire_notifications_and_join_requests`, result `deleted` only).
- [x] 11.6 Squash the branch migrations into `83b81adf7450` on `c9acb7dd3ad0`.
- [x] 11.7 Turning a type off hides it instead of deleting (owner decision); frontend: one interaction handler, silent 404/403, Refuse left / Accept right, the bell refreshes only itself, i18n per type under `rework.notifications.types`.

## 9. Verification

- [x] 9.1 control-plane: `make test && make code-quality && make db-check-heads && make db-check-sqlite`, plus `ruff check --select I` and basedpyright, all green.
  - Done: `make test`: 2046 passed, 10 skipped; `make code-quality` (ruff, `ruff check --select I`, format, bandit, detect-secrets, basedpyright 0 errors) green; `make db-check-heads` and `make db-check-sqlite` green.
- [x] 9.2 Frontend without wiping a running Vite (warn the developer first; never through a symlinked worktree `node_modules`): `npx tsc --noEmit && npx prettier --check src && npx eslint src && npx vitest run src/rework/features/notifications src/rework/components/shared src/rework/features/helpCenter`.
  - Done in the worktree's own `node_modules` (no Vite running there): `make code-quality` (tsc, prettier, eslint) green; `make test`: 363 files passed, 1 skipped; 4458 tests passed, 8 skipped.
- [x] 9.3 Run the `fred-performance-reviewer` skill on the polling endpoint and the emission hooks.
  - Done: backend half, checklist applied by hand: the summary is one `count(*)` on the partial unseen index (async engine, no in-memory state); emission adds one entry read per real agent save and one batched insert per removal, never in a request's critical path on failure. Open point: `notification_type` is not in `PROMETHEUS_ALLOWED_LABELS`, so per-type counts reach OpenSearch only. Frontend half, by hand: one summary request per visible tab every 15 s, none while hidden, a returning tab's focus and visibility refetches collapse into one in-flight request (RTK skips a refetch while one is pending), the list is fetched only while the popover is open, no held connection.
- [x] 9.4 Manual check on a local stack with two users: B edits an agent A published → A's badge appears within 15 s; opening the popover resets it; B republishes → A sees "Handled by B"; a platform admin removes the entry → A gets the removal tile with the reason; delete and clear all work.
  - Done (2026-10-22, owner-run): two users on the worktree frontend (Vite :5174) against a worktree control-plane (:8223, scratch database `fred_notif`, copy of the local `fred` database); fred-agents and knowledge-flow were the shared local services. Confirmed: republish-needed badge, popover resets the badge, "Handled by" after republish, platform-admin removal with its reason, the tile opens the edited agent, full text shown, delete one and clear all, rail layout (profile on top, bell below, divider). A second user's CGU 403 was a split-setup artefact (fred-agents reads the `fred` database), not a defect.
- [x] 9.5 Record the exact command outputs in a `verification.md` before archiving.
  - Done: `verification.md`.
