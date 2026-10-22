## Why

Fred cannot tell one user that something needs them. An editor who changes a published agent and chooses "Ignore" leaves it Modified with nobody else told; an entry removed by a platform admin or an automatic rule reaches its publisher only if they open the team's Agents page. Team join requests were dropped for the same reason, and quota boost requests (#3223) need it too.

Tracking: GitHub issue #3232. Design and catalogue: `docs/swift/rfc/NOTIFICATIONS-RFC.md` (this change is its slice 1).

## What Changes

- **Notification store in control-plane.** One row per recipient: type, team, group key, payload (ids plus a display snapshot), seen, read, handled and expiry timestamps. Text is rendered by the frontend from type and payload.
- **Emitter service.** `notify(...)` and `resolve(...)`, called in-process by domain services after their commit, best effort. Re-emitting an open subject updates it without re-badging.
- **Caller-scoped API.** Unseen count, paginated list (newest first), mark all seen, mark one read, delete one, clear all. No route creates a notification.
- **Bell in the far-left app bar** with an unseen-count badge, polled every 15 s while the tab is visible. Clicking it opens a popover over the nav panel: "Clear all", tiles newest first, an empty state. Opening it resets the badge; a tile disappears once its recipient acts on it (click, button, or its always-visible close button).
- **Action-button framework.** A type declares its buttons; a button calls the existing domain endpoint or navigates. A handled notification shows "Handled by <name>" instead of buttons.
- **30-day expiry.** Reads exclude expired rows; the lifecycle workflow deletes them. A deleted user's or team's rows are deleted.
- **First two types** (triggers already exist):
  - `agent.republish_needed`: another editor changed a published agent; sent to its publisher; resolved when the entry is republished or removed.
  - `agent.marketplace_removed`: the entry entered the Removed state (platform admin or automatic rule) without the publisher causing it; sent to its publisher.
- **`published_by` on marketplace entries**, written on every publish and republish. Older entries have none and notify nobody until republished.
- **Help Center** fr+en page on notifications.
- **Platform switch per type** (owner decision, 2026-10-22): a platform admin page "Notifications" lists every type the backend knows, each with a sentence on when it is sent and to whom and an on/off switch. Platform-wide only; every type on by default. Turning a type off stops sending it and deletes its sent notifications for everyone; turning it back on only affects new events. The underlying actions stay where they are (e.g. Members > Pending requests).
- **Failed tile actions are reported**: an Accept/Refuse that fails with anything but a 404 shows the app's error toast instead of failing silently.

Out of scope: join requests (slice 2, through a new opt-in "on request" team access mode) and quota boost requests (slice 3, sent to the admins of the requester's teams), email or any other channel, per-user or per-team preferences, toasts announcing a notification.

## Capabilities

### New Capabilities

- `notifications`: per-recipient in-app notifications with a bell menu, seen/read/handled state, actions, expiry, and the two marketplace notification types.

### Modified Capabilities

None. The marketplace triggers are specified in `notifications`; the marketplace behaviour itself does not change.

## Impact

- Backend (control-plane): new `notifications` package (`api`, `service`, `store`, `schemas`) and `models/notification_models.py`; one linear Alembic revision on the current head (table + `agent_marketplace_entries.published_by`); hooks in `product/service.py` (`update_agent_instance`) and `agent_marketplace/` (publish, removal); expiry step in the Temporal `LifecycleManagerWorkflow`; cleanup in user and team deletion; `authz-endpoint-matrix.yaml`.
- Platform switch: `disabled_notification_types` table (Alembic `83b81adf7450`), `GET /admin/platform/notification-types`, `PUT /admin/platform/notification-types/{notification_type}` (`can_manage_platform`), admin page `NotificationsPage` at `/admin/notifications`.
- Frontend: regenerated `controlPlaneOpenApi.ts`, aliases in `controlPlaneApiEnhancements.ts`; bell in `MainNavBar`; new `NotificationsPopover` and `NotificationTile`; fr+en strings; Help Center fr+en.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry, `COMPONENT-UX.md`, migration note (minor: schema migration, no operator action).
