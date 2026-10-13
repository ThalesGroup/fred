## Why

In Platform access > Whitelist > Users the page never shows the whitelist (GitHub issue #3086). It lists or searches every known user, so an administrator has to read source chips row by row to find who holds an individual exception, and rows come back ordered by technical user id. The whitelist is defined as exceptions that complement the rule; on a platform with thousands of users the tab must show those exceptions, not the directory.

## What Changes

- `GET /admin/platform/access/users` gains the optional query parameter `exceptions_only` (default `false`). When `true`, the page and `total` cover only users holding an individual exception (manual or initial import).
- Without the parameter the endpoint returns rows in a stable alphabetical order: case-insensitive username, users without a username last, user id as tiebreaker; the answer is otherwise unchanged. With the parameter, the most recently granted exceptions come first, the alphabetical rule breaking ties.
- Whitelist > Users lists individual exceptions only, newest first, server-paginated with the real total; the search narrows that list. Each row shows when the access was added, its origin (manual or initial import) and the person's other access sources, and offers "Remove". An empty "other access" cell means removing the person makes them lose access.
- The response shape does not change: the grant date and the origin are read from the individual source each row already carries.
- Row selection and the bulk bar leave this table: they only served granting, and there is no bulk-remove endpoint.
- An "Add users" button opens a dialog built on the same shell as the team "Add members" dialog: a search across all known users, a pending selection that survives successive searches, people who already hold an individual exception shown as such and not selectable, one confirm action using the existing bulk grant.
- An empty whitelist gets its own short state pointing to the add button, distinct from a search without match.
- French and English strings updated; unused keys deleted. Generated OpenAPI and frontend client regenerated.

No migration, no new endpoint, no change to how admission sources are computed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: "Platform administrators manage live exceptions" (the user listing shows individual exceptions by default, is ordered alphabetically, and people are added through a search dialog) and "Access administration has readable section navigation" (no user selection lives on the page any more; search and paging survive tab changes).

## Impact

- `libs/fred-core/fred_core/security/platform_access/store.py` (filter, ordering, count) and its tests.
- `apps/control-plane-backend/control_plane_backend/platform_access/{api,service}.py`, its tests, regenerated `openapi.json`.
- `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts` (regenerated).
- `apps/frontend/src/rework/components/pages/admin/PlatformAccessPage/` (page, new add dialog, tests).
- The team "Add members" dialog: its layout moves into a shared shell that both dialogs render; its props and behaviour do not change. `Autocomplete` gains one optional prop for its empty-menu message.
- `apps/frontend/src/locales/{fr,en}/translation.json`.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`, `docs/swift/ux/COMPONENT-UX.md`, one migration note (impact: none).
- The public access pages and the rule tester are not edited; the rule tester keeps calling the users query without the filter.
