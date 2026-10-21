## 1. Control-plane model and migration

- [x] 1.1 Add `models/notification_models.py` (`NotificationRow`: `id`, `recipient_id`, `type`, `team_id`, `group_key`, `payload` JSON, `created_at`, `expires_at`, `seen_at`, `read_at`, `handled_at`, `handled_by`, `handled_outcome`) with indexes `(recipient_id, created_at DESC, id)`, partial `recipient_id WHERE seen_at IS NULL`, `expires_at`, and the unique partial `(recipient_id, group_key) WHERE handled_at IS NULL`; register it in `models/table_ownership.py`; verify `make test` in `apps/control-plane-backend`.
  - Done: `models/notification_models.py`; list index ascending `(recipient_id, created_at, id)` (backward scan serves DESC), unique open-group index ordered `(group_key, recipient_id)` so `resolve` uses it; extra nullable `handled_by_name` (display snapshot for "Handled by"). `make test` green.
- [x] 1.2 Add nullable `published_by` to `AgentMarketplaceEntryRow` (`models/agent_marketplace_models.py`); verify existing marketplace tests pass.
  - Done: `AgentMarketplaceEntryRow.published_by`; `tests/test_agent_marketplace.py` green.
- [ ] 1.3 Create one Alembic revision creating `notifications` and adding `agent_marketplace_entries.published_by`, `down_revision` = the current single head (re-parent if `swift` moved; never `alembic merge`), downgrade dropping both; verify `make db-check-heads` (one head) and `make db-check-sqlite` pass, then `make db-upgrade`, `make db-downgrade`, `make db-upgrade` against a real Postgres.
  - Partly: revision `fe166447f3d5` (down `c9acb7dd3ad0`); `make db-check-heads` (one head) and `make db-check-sqlite` (upgrade, `alembic check`, downgrade base) pass; Postgres verified offline only (`alembic upgrade c9acb7dd3ad0:fe166447f3d5 --sql` and the downgrade render the expected DDL). A real `db-upgrade`/`db-downgrade` against Postgres is still to run: no credentials were available in the worktree.

## 2. Control-plane service

- [x] 2.1 Add `notifications/schemas.py`: `NotificationType` enum (`agent.republish_needed`, `agent.marketplace_removed`), one payload model per type, `NotificationView`, `NotificationPage`, `NotificationSummary`; verify payload validation tests (unknown type, missing field).
  - Done: `notifications/schemas.py`; the view is a union discriminated by `type`, one payload model per type, so the generated client types each payload. `tests/test_notifications.py`.
- [x] 2.2 Add `notifications/store.py` (async SQLAlchemy, `announcements/store.py` pattern): upsert by `(recipient_id, group_key)` keeping `seen_at`/`read_at`, batched insert for many recipients, unseen count, cursor page, mark seen up to a cursor, mark read, delete one, delete all, resolve group, delete expired in batches, delete by user, delete by team; every caller-facing query filters `recipient_id` and `expires_at > now()`; verify store tests for each, including that a repeat emission does not reset `seen_at` and that a resolved group accepts a new row.
  - Done: `notifications/store.py`; the cursor is opaque `<created_at µs>.<id>`; an expired open row is replaced by a new emission. `tests/test_notification_store.py` (13 tests).
- [x] 2.3 Add `notifications/service.py`: `notify(recipients, type, payload, group_key, team_id)` and `resolve(group_key, actor_uid, outcome)` (actor's row deleted, others handled), both best effort (warning with ids only, `notifications_created_total{type}` and a failure counter); verify tests: a store exception does not raise, the actor's row disappears, other recipients see `handled_by`.
  - Done: `notifications/service.py`; counters `notifications.created_total` (dim `notification_type`, not a Prometheus label, so OpenSearch only) and `notifications.emit_failed_total` (`status`). `tests/test_notifications.py`.
- [x] 2.4 Wire the store and service in `app/context.py` and `product/dependencies.py`; verify the app starts in tests.
  - Done: container `get_notification_service`/`get_notification_store`; optional `get_notification_service` on product and team deps; the agent store receives the service.

## 3. Control-plane API

- [x] 3.1 Add `notifications/api.py`: `GET /notifications/summary`, `GET /notifications` (`limit` ≤ 50, `before` cursor), `POST /notifications/seen` (`up_to` id), `POST /notifications/{id}/read`, `DELETE /notifications/{id}`, `DELETE /notifications`; mount in `main.py`; another user's id answers 404; verify API tests for each route including the 404 and the expired-row exclusion.
  - Done: `notifications/api.py` mounted in `main.py`; `seen` answers `NotificationSummary`, `read`/`delete`/clear 204; route, 404, 422 and 401 tests in `tests/test_notifications.py`.
- [x] 3.2 Add the six routes to `docs/swift/platform/authz-endpoint-matrix.yaml` as `authenticated_user`; verify the authz matrix test passes.
  - Done: six `authenticated` entries (`pending_review`); `tests/test_authz_endpoint_matrix.py` green.
- [x] 3.3 Delete a user's notifications in `delete_user` (`users/api.py`, next to `delete_seen_for_user`) and a team's in team deletion; verify a test for each.
  - Done: `delete_user` (`tests/test_user_delete_route.py` call order) and `delete_team`, before the team row (`test_team_deletion_deletes_the_teams_notifications`).

## 4. Expiry

- [x] 4.1 Add `run_notification_expiry_once` to `scheduler/lifecycle_runner.py` (batches of 1000, 30 s budget), an activity in `scheduler/temporal/activities.py`, a step in `LifecycleManagerWorkflow` and in the memory runner (`POST /lifecycle/run-once`); verify tests: rows past `expires_at` deleted, others kept, the budget stops the loop.
  - Done: `run_notification_expiry_once` (clock injected: `workflow.time` in Temporal, `time.monotonic` in memory), activity `delete_expired_notifications`, registered in the worker; `LifecycleManagerResult.notifications`. `tests/test_memory_lifecycle_runner.py` (batches, budget, dry run, activity on SQLite).

## 5. Marketplace triggers

- [x] 5.1 Write `published_by = user.uid` in `save_publication` on publish and republish (`agent_marketplace/store.py`, from `publish_agent`); verify a test for both.
  - Done: `save_publication(published_by=...)`; `test_publish_and_republish_record_the_publisher`.
- [x] 5.2 In `update_agent_instance` (`product/service.py`), after the store update and commit, emit `agent.republish_needed` when the save changed the agent, the entry is Published, and `published_by` is set and differs from the editor (group `agent_republish:<entry_id>`, payload: team, agent, entry ids and names, editor name); verify tests: emitted for another editor, not for the publisher, not for a no-op save, not for a legacy entry, a second save does not re-badge.
  - Done: `agent_marketplace/notifications.py::notify_republish_needed`, called from `update_agent_instance`; tests for another editor, publisher, no-op, legacy entry, second save, failing store.
- [x] 5.3 Resolve `agent_republish:<entry_id>` on republish and on removal; verify the publisher's own republish deletes their row and another editor's republish marks it handled.
  - Done: `resolve_republished` after `save_publication`; every removal resolves the group with outcome `removed` (deactivation, suspension and deletion paths carry no actor name). `test_republishing_resolves_the_request`.
- [x] 5.4 Emit `agent.marketplace_removed` wherever an entry enters the Removed state (`unpublish_agent` with a platform reason, `remove_published_entries` callers) unless the actor is the publisher, batched for bulk removals (group `agent_removed:<entry_id>:<removed_at>`, payload with the reason code and the admin message); verify tests: platform-admin removal, automatic removal (team made private), removal by a team editor emits nothing, bulk switch-off emits one row per entry in one insert.
  - Done: `notify_unpublished` at every `emit_unpublished` site: unpublish, switch-off (default and team), team made private, deactivation, suspension, deletion (resolve only). Tests: platform admin, team private, team removal, bulk switch-off (one insert of 2), deactivation by another editor.

## 6. API client

- [x] 6.1 Regenerate without wiping a running Vite: `cd apps/control-plane-backend && make generate-openapi`, then `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`; verify `controlPlaneOpenApi.ts` gains the routes and nothing is hand-edited.
  - Done: `make generate-openapi`, then `make update-control-plane-api` after a real `npm ci` in the worktree; only additions in `controlPlaneOpenApi.ts`; `npx tsc --noEmit` and prettier green.
- [ ] 6.2 In `controlPlaneApiEnhancements.ts`: a `ControlPlaneNotification` tag, summary and list providing it, every mutation invalidating it, friendly aliases (`useNotificationSummaryQuery`, `useNotificationsQuery`, `useMarkNotificationsSeenMutation`, `useMarkNotificationReadMutation`, `useDeleteNotificationMutation`, `useClearNotificationsMutation`); verify `npx tsc --noEmit`.

## 7. Frontend

- [ ] 7.1 Add a notification type registry under `rework/features/notifications/` (type → icon, category, i18n keys, link builder, buttons; unknown types render a generic tile); verify a vitest for both v1 types and an unknown type.
- [ ] 7.2 Add the `NotificationTile` molecule: category icon, title, body, relative time, unread style until clicked (click marks read and follows the link), delete IconButton (`size="medium"`, `color="on-surface-retreat"`), the type's buttons, "Handled by <name>" instead of buttons once handled; design tokens only, `outline-*` borders, full `surface-` names; verify vitest for unread, read, handled and delete.
- [ ] 7.3 Add the `NotificationsPopover` following the `UserProfile` popover pattern (anchored to the rail, over the nav panel, outside click and Escape close it): header with "Clear all", tiles newest first, load more, empty state; opening it fetches the list and posts `seen` up to the newest listed id; verify vitest for open, seen call, clear all, empty state, Escape.
- [ ] 7.4 Add the bell entry to `MainNavBar.tsx` with `IconButton badgeCount` from `useNotificationSummaryQuery` polled every 15 s while the tab is visible (paused when hidden, refetched on focus and visibility change); the count goes into the `aria-label`; verify vitest for badge shown, hidden at 0, aria-label, no polling while hidden.
- [ ] 7.5 Add fr + en strings (`rework.notifications.*`, `rework.mainNav.notifications`); verify `npx tsc --noEmit` and no missing-key warnings in touched tests.

## 8. Docs, Help Center and migration note

- [ ] 8.1 Add `rework/features/helpCenter/content/{fr,en}/features/notifications.md` (what the bell shows, seen vs. read, clear and delete, 30-day expiry, the two marketplace notifications, legacy entries without a publisher); verify `helpCenter/content.test.ts`.
- [x] 8.2 Add a dated numbered entry to `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (routes, caller scope, `published_by`, expiry); verify it follows the latest section's format.
  - Done: §68 of `CONTROL-PLANE-PRODUCT-CONTRACT.md`.
- [x] 8.3 Write `docs/swift/ops/migrations/add-in-app-notifications.md` from the template, impact `minor` (Alembic migration, no operator action); verify `make migration-check` from the repo root.
  - Done: `docs/swift/ops/migrations/3232-add-in-app-notifications.md`; `make migration-check`: "Migration notes valid: 1 new declaration(s)".
- [ ] 8.4 Update `docs/swift/ux/COMPONENT-UX.md` for `NotificationTile`, `NotificationsPopover` and the bell entry.
- [ ] 8.5 Update `docs/swift/rfc/NOTIFICATIONS-RFC.md` status: slice 1 shipped, folded into the `notifications` spec.

## 9. Verification

- [x] 9.1 control-plane: `make test && make code-quality && make db-check-heads && make db-check-sqlite`, plus `ruff check --select I` and basedpyright, all green.
  - Done: `make test`: 2046 passed, 10 skipped; `make code-quality` (ruff, `ruff check --select I`, format, bandit, detect-secrets, basedpyright 0 errors) green; `make db-check-heads` and `make db-check-sqlite` green.
- [ ] 9.2 Frontend without wiping a running Vite (warn the developer first; never through a symlinked worktree `node_modules`): `npx tsc --noEmit && npx prettier --check src && npx eslint src && npx vitest run src/rework/features/notifications src/rework/components/shared src/rework/features/helpCenter`.
- [x] 9.3 Run the `fred-performance-reviewer` skill on the polling endpoint and the emission hooks.
  - Done: backend half, checklist applied by hand: the summary is one `count(*)` on the partial unseen index (async engine, no in-memory state); emission adds one entry read per real agent save and one batched insert per removal, never in a request's critical path on failure. Open point: `notification_type` is not in `PROMETHEUS_ALLOWED_LABELS`, so per-type counts reach OpenSearch only. Frontend polling still to review.
- [ ] 9.4 Manual check on a local stack with two users: B edits an agent A published → A's badge appears within 15 s; opening the popover resets it; the tile stays unread until clicked; B republishes → A sees "Handled by B"; a platform admin removes the entry → A gets the removal tile with the reason; delete and clear all work.
- [ ] 9.5 Record the exact command outputs in a `verification.md` before archiving.
