## Why

Real-consumer validation in fred-agent/fred-agent-evaluator#53 exposed missing row activation, drawer localization and outcome-card tones in the unpublished UI alpha.3 candidate. The developer approved completing these APIs in both repositories.

## What Changes

- Add optional typed DataTable row activation, excluding embedded controls, with keyboard activation.
- Add an optional consumer-owned InlineDrawer close label.
- Add optional KpiStatCard outcome tone using the existing StatusBadge tone vocabulary and design tokens.
- Rebuild the actual alpha.3 archive and verify the evaluator consumes these APIs without changing registry manifests before publication.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `frontend-package-archives`: consumer-owned row interaction, localized drawer dismissal and outcome styling.

## Impact
Canonical shared components, archive fixtures/tests and documentation in Fred #2887; hosted evaluator #53 consumes the additive APIs. Defaults preserve current callers. No release publication or backend changes. Scope and acceptance were confirmed by the developer in this session before implementation.
