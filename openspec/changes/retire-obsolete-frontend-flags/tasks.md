## 1. Retire unsupported flag fields

- [x] 1.1 Remove the retired fields from the control-plane frontend flag model and verify the bootstrap test publishes exactly the three supported flags.
- [x] 1.2 Regenerate control-plane configuration, Helm values, OpenAPI, and frontend TypeScript schemas, and list supported default-off flags in chart values; verify schema drift checks and inspect the generated diff.

## 2. Preserve supported behavior and guide operators

- [x] 2.1 Verify the shared frontend feature-flag hook still fails closed and supported flags remain configurable with its focused tests and a frontend build.
- [x] 2.2 Update the PR migration note for private overlays containing retired keys and verify `make migration-check` passes.

## 3. Confirm repository and PR state

- [x] 3.1 Search all tracked files for the retired key names and verify there are no occurrences while `feature_flags` and current flag names remain.
- [x] 3.2 Run the applicable root quality gate and backend/frontend tests, record results in the draft PR, and verify its diff contains only intended changes.
