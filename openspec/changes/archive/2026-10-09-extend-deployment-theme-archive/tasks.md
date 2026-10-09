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

Verification: frontend typecheck, production build, ESLint, focused tests, sample ZIP build, and container smoke passed. Local k3d loaded the ZIP from SeaweedFS with all four deployments ready. The user selected the added theme and confirmed its colors and chat appearance after CSS priority and background refinements. An independent review found the preview selector mismatch; the sample selectors and regression test were corrected.
