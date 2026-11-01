## Why

Nothing tells a user that something needs them. When another editor changes an agent they published, or the marketplace removes it, the publisher only finds out by opening the team's Agents page. GitHub issue #3232.

## What Changes

- Control-plane notification store and caller-scoped API: unseen count, list, mark seen, delete one, clear all. No route creates a notification.
- A bell in the app bar with an unseen badge (polled every 15 s) and a popover of tiles.
- Two types: `agent.republish_needed` and `agent.marketplace_removed`, sent to the agent's publisher (`agent_marketplace_entry.published_by`, new).
- 30-day expiry in the lifecycle job.
- A platform admin page to turn each type on or off.

Out of scope: team join requests (`add-team-join-requests`), other channels, preferences, toasts.

## Capabilities

### New Capabilities

- `notifications`: per-recipient in-app notifications, the bell, expiry, the platform switch and the two marketplace types.

### Modified Capabilities

None.

## Impact

Control-plane `notifications/` package, Alembic revision `83b81adf7450`, marketplace and team hooks, lifecycle step; fred-core `KPIMiddleware` `skip_suffixes`; regenerated client; bell, popover, `NotificationTile`, admin page, Help Center fr+en.
