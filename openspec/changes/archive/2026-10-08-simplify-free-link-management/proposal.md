## Why

The invitation manager currently mixes history and generation fields, its long opening-count heading is truncated, and copying an existing link requires revealing it first. Administrators need a list-first flow with a focused creation form and explicit clipboard actions. Follow-up to issue #2965 and PR #2966, separate from the filter-editor refinement.

## What Changes

- Open Manage links on the paginated history with a Create link action, without showing note/expiry inputs initially.
- Open a separate creation dialog with the optional note followed by optional expiration; reuse the platform KPI popover presentation with a single future date, duration shortcuts and Apply.
- Replace Show URL with Copy URL: explicitly recover the existing invitation and copy it, then confirm clipboard success.
- After creation, show the generated URL with an immediate Copy URL action. If clipboard access fails, retain the usable URL and explain the manual-copy fallback without claiming link creation failed.
- Use the short localized column heading Clicks, preserving the authenticated-opening count and its explanatory text.
- Preserve pagination, statuses, independent revocation, Free suspension, expiry validation and own-admin uncached recovery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: list-first invitation administration, separate creation, shared date selection and explicit reliable clipboard feedback.

## Impact

PlatformAccessLinkManager, existing KPI selector styles and shared DateTimeInput consumption, English/French translations, styles and focused UI tests. Reuse the generated creation/reveal/revoke APIs; no backend API, migration, tracking-table or Helm changes. Update existing UX/operator docs and PR screenshots. Commit link UI separately from the filter-editor changes.
