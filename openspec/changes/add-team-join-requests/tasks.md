## 1. Access mode and model

- [ ] 1.1 Add `JoiningMode.ON_REQUEST = "on_request"` (`libs/fred-core/fred_core/teams/metadata_store.py`, docstring updated); extend the `update_team` rule so a private result turns `open` or `on_request` into `invite_only`, and refuse the team's pending requests whenever it leaves `on_request` (decision 8); verify tests in `apps/control-plane-backend` for both downgrades, for a public team accepting `on_request`, and for the automatic refusal with its notifications.
- [ ] 1.2 Keep `_LEGACY_JOINING_MODES` (`import_export/importer.py`) mapping `request_only`/`closed` to `invite_only`, reword its comment (legacy default, not an opt-in), and let `on_request` through; verify an import test for each value.
- [ ] 1.3 Add `models/team_join_request_models.py` (`TeamJoinRequestRow`: `id`, `team_id`, `requester_id`, `requester_name`, `message` ≤ 280, `status` `pending`|`refused`, `created_at`, `expires_at` (30 days pending, 7 days after a refusal), `decided_at`, `decided_by`; unique `(team_id, requester_id)`; indexes `requester_id`, `expires_at`) and register it in `models/table_ownership.py`; verify `make test`.
- [ ] 1.4 Create one Alembic revision, `down_revision = "fe166447f3d5"` (re-parent if the branch head moved; never `alembic merge`), creating `team_join_requests`; downgrade rewrites `teammetadata.joining_mode = 'on_request'` to `invite_only` and drops the table; verify `make db-check-heads` (one head), `make db-check-sqlite`, and upgrade / downgrade / upgrade against a real Postgres copy (not the owner's `fred` database).

## 2. Join request service

- [ ] 2.1 Add `teams/join_requests.py` with a store (async SQLAlchemy, every read ignoring expired rows) and service functions `create`, `cancel_mine`, `list_mine`, `list_pending`, `accept`, `refuse`, following decisions 4 to 8 of `design.md`; verify unit tests: first ask, repeat ask returns the pending row and emits nothing, 409 not on request, 409 already member, 409 `join_request_refused` within 24 hours of a refusal, a new request replaces a refusal older than 24 hours, an expired row is replaced, accept grants `team_member` only and deletes the row, accept of an existing member is a no-op grant, refuse keeps the row 7 days, accept anyway on a refused row grants and deletes it, decisions on a missing row raise not found, leaving `on_request` refuses every pending row.
- [ ] 2.2 Emit `team.join_request.created|cancelled|accepted|refused` with `emit_audit_log` (ids only, never the message); verify a test asserting the fields and the absence of the message.
- [ ] 2.3 Delete a team's requests in `delete_team` and a user's requests (plus the admins' open notification groups) in `delete_user`; verify a test for each.
- [ ] 2.4 Delete expired requests in the lifecycle notification step (`run_notification_expiry_once`, same batches and budget) and report the count in `LifecycleManagerResult.notifications`; verify the memory lifecycle runner test.

## 3. Control-plane API

- [ ] 3.1 Add routes in `teams/api.py`: `POST /teams/{team_id}/join-requests` (body `CreateTeamJoinRequest.message`, 201 new / 200 existing), `DELETE /teams/{team_id}/join-requests/mine` (204), `GET /teams/join-requests/mine` (`list[MyTeamJoinRequest]`), `GET /teams/{team_id}/join-requests` (`can_administer_members`, `list[TeamJoinRequest]`, pending and refused), `POST /teams/{team_id}/join-requests/{request_id}/accept` (pending or refused: "Accept anyway") and `/refuse` (`can_administer_members`, 204); map the errors to 404 `join_request_not_found`, 409 `team_not_on_request`, `already_team_member`, `join_request_refused`; confirm the routes sit behind the same platform-access gate as `POST /teams/{team_id}/join`; verify API tests for each route and status, including 403 for a non-admin decision and 401 unauthenticated.
- [ ] 3.2 Add the six routes to `docs/swift/platform/authz-endpoint-matrix.yaml`; verify `tests/test_authz_endpoint_matrix.py`.
- [ ] 3.3 Regenerate the client (`cd apps/frontend && make update-control-plane-api`) and add friendly aliases in `controlPlaneApiEnhancements.ts` with cache tags: decisions invalidate the team's members, its pending requests and the notifications; ask and cancel invalidate `mine`.

## 4. Notification types

- [ ] 4.1 In `notifications/schemas.py` add `team.join_requested` (`TeamJoinRequestedPayload`: `team_id`, `team_name`, `request_id`, `requester_id`, `requester_name`, `message`) and `team.join_request_answered` (`TeamJoinRequestAnsweredPayload`: `team_id`, `team_name`, `outcome`), their views in the `NotificationView` union, `ACTION_PERMISSION` typed `TeamPermission | None` with `CAN_ADMINISTER_MEMBERS` and `None`; make `forget_lost_access` skip `None`; update `test_every_type_declares_the_permission_to_act_on_it` so `None` is allowed only for types sent without a team; verify `tests/test_notifications.py`.
- [ ] 4.2 Add `NotificationStore.delete_groups(group_keys)` and `NotificationService.delete_groups` (best effort); verify a store test.
- [ ] 4.3 Wire emission after commit in the service: create → `notify` to the team's `team_admin` users with `team_id` (group `join_request:<id>`); accept/refuse/automatic refusal → `resolve` with outcome and actor, then `notify` the requester without `team_id` (group `join_request_outcome:<id>`; accept anyway deletes that group's refusal first); cancel and user deletion → `delete_groups`; verify tests: an editor and a pending admin get nothing, a demoted admin's row is deleted, the deciding admin's row disappears and the other shows "handled by", the requester's answer reaches a non-member, an emission failure does not fail the decision.

## 5. Frontend

- [ ] 5.1 `TeamSettingsParameters`: three-item ButtonGroup Open / On request / Invite only for public teams (private unchanged); fr+en strings; verify `TeamSettingsParameters.test.tsx`.
- [ ] 5.2 `MarketplaceTeams` fetches `mine` once and passes each team's request to `TeamCard`; `TeamCard` renders the `on_request` states ("Ask to join" opening the shared `Dialog` with an optional `TextArea`, guidance in `description`, 280 max; "Request sent" + "Cancel request"; "Request declined"); fr+en strings; verify `TeamCard.test.tsx` for each state, ask and cancel.
- [ ] 5.3 `TeamSettingsMembers`: "Pending requests" section for `can_administer_members` holders, only when the list is not empty, rows with name, message, date, Accept and Refuse when pending, Accept anyway when refused; verify `TeamSettingsMembers.test.tsx` (hidden when empty or not admin, actions call the endpoints).
- [ ] 5.4 `notificationTypes.ts`: renderers for both types (icons, `action_required` and `information` categories, title/body with message, links to `/team/<id>/settings/members` and `/team/<id>/agents`, `call` actions Accept (primary) and Refuse, "Open the team" navigate when accepted); a 404 from a `call` action deletes the notification; fr+en strings; verify `notificationTypes.test.ts` and `NotificationsPopover.test.tsx`.
- [ ] 5.5 Run `make code-quality` and `make test` in `apps/frontend` only after telling the owner, since they wipe the running Vite's `node_modules/.vite`; restart that Vite afterwards with their OK.

## 6. Docs

- [ ] 6.1 Help Center fr+en: `features/teams-and-permissions.md` (the On request mode, asking, cancelling, deciding, the Members section) and `features/notifications.md` (the two new types); verify `content.test.ts`.
- [ ] 6.2 `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entry after §69 (`on_request`, routes, error codes, record lifecycle, notification types) and a one-line pointer from §29 to it; extend §69's union list.
- [ ] 6.3 `docs/swift/ux/COMPONENT-UX.md`: TeamCard states, three-way access mode, Pending requests section.
- [ ] 6.4 Update `docs/swift/ops/migrations/3232-add-in-app-notifications.md`: title and applicability cover join requests, the second revision in Upgrade and Rollback, a validation step for a request; impact stays minor, configuration none.
- [ ] 6.5 `NOTIFICATIONS-RFC.md`: mark slice 2 as implemented once done.

## 7. Verification

- [ ] 7.1 Control-plane `make code-quality`, `make test`, `ruff check --select I` and basedpyright on touched files.
- [ ] 7.2 Run the `fred-performance-reviewer` skill on the notification emission and decision paths.
- [ ] 7.3 Live check with the owner (two browser users, a public team): opt in, ask with a message, see the badge within 15 s, accept from the tile, second admin sees "Handled by", requester gets the answer and finds the team under "Your teams"; repeat with refuse and with cancel; switch the team private and check the mode.
- [ ] 7.4 Record the evidence in `verification.md`, reconcile divergences in `design.md`, then archive after `add-in-app-notifications`.
