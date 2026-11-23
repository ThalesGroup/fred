# Proposal

## Why

In PR #3290, Admin > Features places the platform settings gear beside the team-management action, making the two actions hard to scan. An agent author who uploaded a PowerPoint template can replace it, but the form offers no way to return to the platform default.

## What Changes

- Give platform settings their own rightmost column in the capability table. Show the gear only for a capability with a registered platform settings panel; other rows have an empty cell.
- Let an agent author remove a saved `ppt_builder` template override from either agent form layout. The form shows the platform default (or built-in template) immediately, and Save persists the return to that default.
- Keep clearing an unsaved file selection distinct from removing a saved override. Clear template-specific pattern edits on reset while preserving other presentation settings.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ppt-builder`: Clarify platform settings discovery in Admin > Features and add the agent form action for returning from an uploaded template to the platform default.

## Impact

- Frontend: `FeaturesPage`, the shared `PptBuilderTemplatePanel` and analysis hook, English and French labels, and focused tests.
- Existing save contract: submit `template_sha256: null` with no staged asset. The pod already clears template-specific overrides and derives `template_key` from the hash; no API, migration or runtime change is planned.
- Tracking: PR #3290, issue #2679.
