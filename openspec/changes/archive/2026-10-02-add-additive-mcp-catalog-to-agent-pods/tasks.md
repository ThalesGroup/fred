## 1. Runtime

- [x] 1.1 Add optional additive catalog loading after installed providers, retaining legacy replacement precedence and rejecting duplicate IDs.
- [x] 1.2 Test package-plus-file, empty/missing files, duplicate IDs and legacy replacement.

## 2. Fred pod and chart

- [x] 2.1 Add the app-owned external catalog file and copy it into the production image.
- [x] 2.2 Render and mount an additive Helm catalog without hiding packaged servers; validate the chart and schema.

## 3. Close-out

- [x] 3.1 Update the current MCP spec and app/operation docs; verify focused suites and root code quality.
- [x] 3.2 Reconcile and archive this change after verification, then update the existing draft PR.
