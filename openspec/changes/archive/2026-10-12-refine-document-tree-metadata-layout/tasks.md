## 1. Implementation

- [x] 1.1 Render nested folders and compact file rows without inline dates; component tests cover nesting, empty folders and historical records.
- [x] 1.2 Reuse metadata tooltips with branding, partial-listing wording and latest-displayed semantics; verify hover, keyboard, Escape and touch on narrow viewports.
- [x] 1.3 Verify stored arrival metadata reaches the current backend renderer without substituting missing dates and verify aligned 20,000/60,000 character budgets with focused tests and regenerated API output.

## 2. Close-out

- [x] 2.1 Obtain independent read-only review, pass targeted tests and root quality, update existing UX/migration guidance and archive the delta.

Verification: 27 Knowledge Flow tests and 51 capability tests passed; the five focused frontend suites passed 170 tests. Headless Chromium checked the actual component on hover, keyboard focus, Escape, the shared mono font and a 320 px touch viewport without overflow or runtime errors. API generation was rerun; the generated client shape is unchanged.

Review: independent read-only review of the working delta against dbb94507de4794d4dc6f41e1deff1133589cad23 covered frontend/parser consumers, budget alignment and backend async rendering. An accidental unrelated content-budget edit was restored before the final review. No actionable finding remains. Full authenticated LLM turns and load testing were excluded.

Close-out: root code-quality passed across all modules using a temporary Control Plane config to exclude two pre-existing untracked generated provisioning scripts and environment/cache directories. Tracked source checks remained enabled; the temporary config was removed. Runtime retains five baseline warnings. Both updated main specs and both changes pass strict validation; repository-wide strict spec validation has one pre-existing placeholder Purpose warning in untouched frontend-surface-scale. Docs are reconciled, the delta is synced and the change is archived.
