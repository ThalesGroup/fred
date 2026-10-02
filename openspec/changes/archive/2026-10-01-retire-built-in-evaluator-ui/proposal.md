## Why

The external evaluator has been validated through Fred's application host. The built-in evaluator now duplicates it and keeps Fred coupled to evaluator-specific screens and API polling. Tracked in #2904; shared UI SDK work remains in #2890.

## What Changes

- Remove the Evaluations team-settings entry and its built-in screens. Old settings/evaluations URLs use the existing unknown-section fallback to Members.
- Remove evaluator-specific RTK client registration, generated snapshot, client generation target, translations and direct evaluator polling, rehydration and event subscriptions.
- Keep evaluation access through registered Apps and retain reusable UI components, evaluation permissions, services and stored data.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-application-hosting`: evaluator functionality belongs to the registered application, not built-in team settings or Activity polling.
- `frontend-package-archives`: preserve the generic StatusBadge contract while retiring the built-in evaluation StatusPill consumer.

## Impact

Frontend team navigation, TeamSettingsPage, TeamSettingsEvaluations, TaskActivity, Redux store, evaluator API slice, locales and Makefile. No backend API or database migration. Deployments relying on the old UI must register the external evaluator application. Update UX guidance and the PR's existing operator migration note; verify navigation, legacy URLs, Activity, hosting and shared UI exports.
