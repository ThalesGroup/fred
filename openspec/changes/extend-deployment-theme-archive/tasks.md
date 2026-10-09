## Implementation

- [x] Extend the ZIP overlay and validate branding properties.
- [x] Load CSS and branding properties before frontend render.
- [x] Extend the sample bundle and operator documentation.
- [x] Verify the frontend merge, ZIP packaging and container serving/fallback.
- [x] Review the branch and reconcile the specification.

Verification: frontend typecheck, production build, focused Vitest and ESLint, shell syntax, sample ZIP build, and the local Docker theme smoke test passed. An independent read-only review against `swift` found no actionable defect in the changed scope. The ZIP was served by a local S3-style test store; no live SeaweedFS deployment was changed.
