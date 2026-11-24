## 1. Backend

- [x] 1.1 `notifications` and `disabled_notification_types` tables, `agent_marketplace_entry.published_by`, revision `83b81adf7450`
- [x] 1.2 Store, service and caller-scoped routes; authz matrix entries
- [x] 1.3 Marketplace triggers: republish needed, removal; resolve on republish or removal
- [x] 1.4 Recipient permission filter; cleanup on role loss, leaving, user and team deletion
- [x] 1.5 Lifecycle expiry step (memory and Temporal)
- [x] 1.6 Platform switch routes
- [x] 1.7 Skip the summary poll in `KPIMiddleware`

## 2. Frontend

- [x] 2.1 Regenerated client, cache tags and aliases
- [x] 2.2 Bell, popover, `NotificationTile`, type registry, fr+en strings
- [x] 2.3 Admin Notifications page
- [x] 2.4 Help Center fr+en

## 3. Verification

- [x] 3.1 `make code-quality`, `make test` (control-plane, fred-core, frontend), `alembic heads` = 1, `alembic upgrade head` on a scratch database
