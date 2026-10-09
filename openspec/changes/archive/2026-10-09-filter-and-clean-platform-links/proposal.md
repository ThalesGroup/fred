## Why

Invitation history becomes hard to navigate as links accumulate. Platform administrators need status filters and a confirmed cleanup of obsolete links without affecting usable invitations or enrolled members. Tracking: #2965, PR #2966.

## What Changes

- Filter a team's complete invitation history by All, Active, Revoked, Expired or Suspended, with matching server pagination.
- Add a confirmed action to permanently delete all revoked or expired links for that team, including rows outside the current page or filter.
- Preserve active and valid suspended invitations, membership, team access settings and independent admission sources.
- Reuse Fred's Select, Button, Dialog and paginated DataTable, with localized feedback and refreshed counts after cleanup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: Status-filtered invitation history and administrator-only bulk cleanup of obsolete link rows.

## Impact

- Control-plane invitation routes, schemas and service; existing SQL link table and mutation transaction (no migration).
- Generated control-plane frontend client, query invalidation and PlatformAccessLinkManager.
- Backend isolation/lifecycle tests, frontend filter/confirmation tests, current UX and product-contract documentation and existing migration guide.
