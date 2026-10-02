## Why

Two retired frontend flags are still published by the control-plane configuration and bootstrap schemas even though no active frontend consumer uses them. Their presence suggests unsupported features remain configurable and leaves stale fields in the generated Helm and TypeScript contracts.

## What Changes

- **BREAKING for overlays that set retired keys:** Remove the two retired fields from the typed frontend flag model and bootstrap response.
- Regenerate the control-plane configuration schema, Helm values schema, and frontend OpenAPI client from their sources.
- Keep the typed `feature_flags` object, its current supported flags, the chart's application gate, and the frontend fail-closed flag hook.
- Document the operator impact if an existing values overlay still sets a retired field.

## Capabilities

### New Capabilities

- `frontend-feature-flags`: Define the supported deployment flag surface from configuration through bootstrap and frontend consumption.

### Modified Capabilities

None.

## Impact

Control-plane configuration and bootstrap, generated API and Helm schemas, frontend generated types, one bootstrap test, and the PR migration note. No database or authorization rule changes. This extends the cleanup tracked by GitHub issue #2910 and draft PR #2914.
