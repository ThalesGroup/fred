## Implementation

- [x] Extend the ZIP overlay and validate branding properties.
- [x] Load CSS and branding properties before frontend render.
- [x] Extend the sample bundle and operator documentation.
- [x] Verify the frontend merge, ZIP packaging and container serving/fallback.
- [x] Review the branch and reconcile the specification.

## Additional selectable themes

- [x] Validate and serve a multi-theme catalog from the deployment ZIP.
- [x] Load the catalog before render and offer added themes in profile and admin selectors.
- [x] Inherit complete shipped theme tokens and document an example theme.
- [x] Verify the container and local serving flow, then review the full branch.

Verification: typecheck, production build, ESLint, 45 focused tests, bundle packaging and container smoke passed. The k3d frontend served the Acme catalog and CSS from SeaweedFS with all four deployments ready. Independent review against `swift` found an admin preview selector mismatch; the example CSS and docs now use preview-compatible selectors, covered by a focused admin test. Browser interaction remains for manual validation.

Verification: frontend typecheck, production build, focused Vitest and ESLint, shell syntax, sample ZIP build, and the local Docker theme smoke test passed. An independent read-only review against `swift` found no actionable defect in the changed scope. The ZIP was served by a local S3-style test store; no live SeaweedFS deployment was changed.
