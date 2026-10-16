## Why

After the initial T0 import, later directory identities cannot be included before filtering activation because both the API and the administration page treat completion as final. Administrators need an explicit refresh with a choice about previously removed people.

Tracking: https://github.com/ThalesGroup/fred/issues/3140.

## What Changes

- Keep the initial import and its completed status. While filtering is off, offer a small refresh icon after completion.
- On every refresh with reliable history, offer "Preserve removals" or "Include removed people". Preview and confirmation describe the selected mode; the second mode warns that removed people can regain access.
- Record individual removals durably so the first mode excludes those identities. Existing grants keep their source, actor and grant date in either mode. Refresh adds missing exceptions; it does not delete other whitelist entries.
- For an existing completed import without reliable removal history, require inclusion mode for the next explicit refresh. Warn that history is unavailable, the entire T0 population will be recalculated and previously removed candidates can regain access. Require confirmation before executing. A successful full refresh establishes the new baseline and makes both modes available. The owner confirms that legacy installations are test environments; do not reconstruct missing history.
- Reuse the configured directory and saved rule, including conservative treatment of unknown evidence. Reject refresh while filtering is on. Keep ordinary completed-import retries, restarts and upgrades inert.
- Serialize refreshes and record one audit summary identifying the selected mode and actual additions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: extend "T0 grandfathering is an explicit fixed snapshot" with explicit refresh, per-refresh mode selection, durable removals and legacy-history warnings. An ordinary retry still keeps the completed snapshot fixed.

## Impact

- Shared SQL models in `libs/fred-core/fred_core/security/platform_access/` and one control-plane Alembic migration, including table ownership and schema checks where required.
- Control-plane `platform_access/{api,schemas,service}.py` and its tests: typed preview and refresh options, removal recording, transactional conflict checks and audit summary.
- Regenerated control-plane OpenAPI and frontend client; existing frontend cache enhancements.
- `PlatformAccessPage` and a focused refresh dialog, French and English translations and component tests.
- Product contract, component UX documentation and one migration note covering schema upgrade and incomplete test-environment history.
- Existing UI changes `whitelist-lists-individual-exceptions` and `condense-platform-access-admin-screens` do not modify the T0 requirement. This separate outcome extends the existing capability without reopening their completed UI work.
