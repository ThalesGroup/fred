# Proposal

## Why
Home suggestions disappear without OpenSearch and never backfill short recent-agent lists. Issue: https://github.com/ThalesGroup/fred/issues/3510.

## What Changes
- Return up to a caller-selected, bounded number of usable instances (five by default), recent conversation activity first, then alphabetical suggestions from accessible default teams and personal space.
- Use SQL metadata and existing authorization instead of KPI history.
- Track activity separately from title/context edits, reusing the existing explicit activity PATCH.
- Replace frontend per-team fan-out with one bounded product query and explicit loading/error states.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `managed-conversations`: durable activity tracking and home agent discovery.

## Impact
Control-plane session metadata migration, product endpoint and generated frontend client, home cards, contract/UX and migration notes. No new table, dependency, cache or runtime-history fan-out.
