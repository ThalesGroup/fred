## 1. Control-plane model and migration

- [ ] 1.1 Add `models/notification_models.py` (`NotificationRow`: `id`, `recipient_id`, `type`, `team_id`, `group_key`, `payload` JSON, `created_at`, `expires_at`, `seen_at`, `read_at`, `handled_at`, `handled_by`, `handled_outcome`) with indexes `(recipient_id, created_at DESC, id)`, partial `recipient_id WHERE seen_at IS NULL`, `expires_at`, and the unique partial `(recipient_id, group_key) WHERE handled_at IS NULL`; register it in `models/table_ownership.py`; verify `make test` in `apps/control-plane-backend`.
- [ ] 1.2 Add nullable `published_by` to `AgentMarketplaceEntryRow` (`models/agent_marketplace_models.py`); verify existing marketplace tests pass.
- [ ] 1.3 Create one Alembic revision creating `notifications` and adding `agent_marketplace_entries.published_by`, `down_revision` = the current single head (re-parent if `swift` moved; never `alembic merge`), downgrade dropping both; verify `make db-check-heads` (one head) and `make db-check-sqlite` pass, then `make db-upgrade`, `make db-downgrade`, `make db-upgrade` against a real Postgres.

## 2. Control-plane service

- [ ] 2.1 Add `notifications/schemas.py`: `NotificationType` enum (`agent.republish_needed`, `agent.marketplace_removed`), one payload model per type, `NotificationView`, `NotificationPage`, `NotificationSummary`; verify payload validation tests (unknown type, missing field).
- [ ] 2.2 Add `notifications/store.py` (async SQLAlchemy, `announcements/store.py` pattern): upsert by `(recipient_id, group_key)` keeping `seen_at`/`read_at`, batched insert for many recipients, unseen count, cursor page, mark seen up to a cursor, mark read, delete one, delete all, resolve group, delete expired in batches, delete by user, delete by team; every caller-facing query filters `recipient_id` and `expires_at > now()`; verify store tests for each, including that a repeat emission does not reset `seen_at` and that a resolved group accepts a new row.
- [ ] 2.3 Add `notifications/service.py`: `notify(recipients, type, payload, group_key, team_id)` and `resolve(group_key, actor_uid, outcome)` (actor's row deleted, others handled), both best effort (warning with ids only, `notifications_created_total{type}` and a failure counter); verify tests: a store exception does not raise, the actor's row disappears, other recipients see `handled_by`.
- [ ] 2.4 Wire the store and service in `app/context.py` and `product/dependencies.py`; verify the app starts in tests.

## 3. Control-plane API

- [ ] 3.1 Add `notifications/api.py`: `GET /notifications/summary`, `GET /notifications` (`limit` ≤ 50, `before` cursor), `POST /notifications/seen` (`up_to` id), `POST /notifications/{id}/read`, `DELETE /notifications/{id}`, `DELETE /notifications`; mount in `main.py`; another user's id answers 404; verify API tests for each route including the 404 and the expired-row exclusion.
- [ ] 3.2 Add the six routes to `docs/swift/platform/authz-endpoint-matrix.yaml` as `authenticated_user`; verify the authz matrix test passes.
- [ ] 3.3 Delete a user's notifications in `delete_user` (`users/api.py`, next to `delete_seen_for_user`) and a team's in team deletion; verify a test for each.

## 4. Expiry

- [ ] 4.1 Add `run_notification_expiry_once` to `scheduler/lifecycle_runner.py` (batches of 1000, 30 s budget), an activity in `scheduler/temporal/activities.py`, a step in `LifecycleManagerWorkflow` and in the memory runner (`POST /lifecycle/run-once`); verify tests: rows past `expires_at` deleted, others kept, the budget stops the loop.

## 5. Marketplace triggers

- [ ] 5.1 Write `published_by = user.uid` in `save_publication` on publish and republish (`agent_marketplace/store.py`, from `publish_agent`); verify a test for both.
- [ ] 5.2 In `update_agent_instance` (`product/service.py`), after the store update and commit, emit `agent.republish_needed` when the save changed the agent, the entry is Published, and `published_by` is set and differs from the editor (group `agent_republish:<entry_id>`, payload: team, agent, entry ids and names, editor name); verify tests: emitted for another editor, not for the publisher, not for a no-op save, not for a legacy entry, a second save does not re-badge.
- [ ] 5.3 Resolve `agent_republish:<entry_id>` on republish and on removal; verify the publisher's own republish deletes their row and another editor's republish marks it handled.
- [ ] 5.4 Emit `agent.marketplace_removed` wherever an entry enters the Removed state (`unpublish_agent` with a platform reason, `remove_published_entries` callers) unless the actor is the publisher, batched for bulk removals (group `agent_removed:<entry_id>:<removed_at>`, payload with the reason code and the admin message); verify tests: platform-admin removal, automatic removal (team made private), removal by a team editor emits nothing, bulk switch-off emits one row per entry in one insert.

## 6. API client

- [ ] 6.1 Regenerate without wiping a running Vite: `cd apps/control-plane-backend && make generate-openapi`, then `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`; verify `controlPlaneOpenApi.ts` gains the routes and nothing is hand-edited.
- [ ] 6.2 In `controlPlaneApiEnhancements.ts`: a `ControlPlaneNotification` tag, summary and list providing it, every mutation invalidating it, friendly aliases (`useNotificationSummaryQuery`, `useNotificationsQuery`, `useMarkNotificationsSeenMutation`, `useMarkNotificationReadMutation`, `useDeleteNotificationMutation`, `useClearNotificationsMutation`); verify `npx tsc --noEmit`.

## 7. Frontend

- [ ] 7.1 Add a notification type registry under `rework/features/notifications/` (type → icon, category, i18n keys, link builder, buttons; unknown types render a generic tile); verify a vitest for both v1 types and an unknown type.
- [ ] 7.2 Add the `NotificationTile` molecule: category icon, title, body, relative time, unread style until clicked (click marks read and follows the link), delete IconButton (`size="medium"`, `color="on-surface-retreat"`), the type's buttons, "Handled by <name>" instead of buttons once handled; design tokens only, `outline-*` borders, full `surface-` names; verify vitest for unread, read, handled and delete.
- [ ] 7.3 Add the `NotificationsPopover` following the `UserProfile` popover pattern (anchored to the rail, over the nav panel, outside click and Escape close it): header with "Clear all", tiles newest first, load more, empty state; opening it fetches the list and posts `seen` up to the newest listed id; verify vitest for open, seen call, clear all, empty state, Escape.
- [ ] 7.4 Add the bell entry to `MainNavBar.tsx` with `IconButton badgeCount` from `useNotificationSummaryQuery` polled every 15 s while the tab is visible (paused when hidden, refetched on focus and visibility change); the count goes into the `aria-label`; verify vitest for badge shown, hidden at 0, aria-label, no polling while hidden.
- [ ] 7.5 Add fr + en strings (`rework.notifications.*`, `rework.mainNav.notifications`); verify `npx tsc --noEmit` and no missing-key warnings in touched tests.

## 8. Docs, Help Center and migration note

- [ ] 8.1 Add `rework/features/helpCenter/content/{fr,en}/features/notifications.md` (what the bell shows, seen vs. read, clear and delete, 30-day expiry, the two marketplace notifications, legacy entries without a publisher); verify `helpCenter/content.test.ts`.
- [ ] 8.2 Add a dated numbered entry to `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (routes, caller scope, `published_by`, expiry); verify it follows the latest section's format.
- [ ] 8.3 Write `docs/swift/ops/migrations/add-in-app-notifications.md` from the template, impact `minor` (Alembic migration, no operator action); verify `make migration-check` from the repo root.
- [ ] 8.4 Update `docs/swift/ux/COMPONENT-UX.md` for `NotificationTile`, `NotificationsPopover` and the bell entry.
- [ ] 8.5 Update `docs/swift/rfc/NOTIFICATIONS-RFC.md` status: slice 1 shipped, folded into the `notifications` spec.

## 9. Verification

- [ ] 9.1 control-plane: `make test && make code-quality && make db-check-heads && make db-check-sqlite`, plus `ruff check --select I` and basedpyright, all green.
- [ ] 9.2 Frontend without wiping a running Vite (warn the developer first; never through a symlinked worktree `node_modules`): `npx tsc --noEmit && npx prettier --check src && npx eslint src && npx vitest run src/rework/features/notifications src/rework/components/shared src/rework/features/helpCenter`.
- [ ] 9.3 Run the `fred-performance-reviewer` skill on the polling endpoint and the emission hooks.
- [ ] 9.4 Manual check on a local stack with two users: B edits an agent A published → A's badge appears within 15 s; opening the popover resets it; the tile stays unread until clicked; B republishes → A sees "Handled by B"; a platform admin removes the entry → A gets the removal tile with the reason; delete and clear all work.
- [ ] 9.5 Record the exact command outputs in a `verification.md` before archiving.
