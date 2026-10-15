## 1. Reuse the existing application

- [x] 1.1 Restore `App` and the existing router as the sole entry; move manager admission into the existing CGU/bootstrap guards and remove the parallel shell and styles. Verify startup, required/disabled/changed CGU, bootstrap, unavailable state and explicit retries with focused frontend tests.
- [x] 1.2 Adapt existing providers, layout, rail, admin panel and account menu to the bounded manager journey; remove mounted Python subscriptions and unsupported route destinations. Verify direct URL denial/redirection, manager-only authority, absence of background calls, and identity/logout both before and after admission; test switching accounts from CGU, bootstrap and admission-error screens.
- [x] 1.3 Adapt the existing home and space list to generated manager memberships and roles, including organization/team/project selection and empty root state. Verify hierarchy, multiple memberships, unchanged role labels, loading/error states and account cache isolation without fake Python DTOs.

## 2. Verify the complete journey

- [x] 2.1 Extend `make test-provisioning-browser` to traverse the real Fred sidebar, admin console and account menu, retaining all previous consent/bootstrap/import/replay/refusal assertions and project fixture coverage. Verify unsupported direct URLs and reject all unexpected control-plane, knowledge-flow and agent-runtime calls; review desktop and narrow-width screenshots for layout, scrolling and keyboard access.
- [x] 2.2 Run frontend `make test`, `npm run build`, repository `make code-quality`, and manager `make test`, `make test-integration`, `make code-quality`. Record outcomes and fixture scope here; fix failures without weakening existing business assertions. Mark tests proving existing invariants with `// Proves: I<n>`.
- [x] 2.3 Apply the branch-review procedure and obtain independent read-only review of the implementation and affected consumers. Record base/head, scope, findings and exclusions here; add a regression test for each actionable defect and obtain review of corrections.

## 3. Reconcile and commit

- [x] 3.1 After review, update the arc42 journey/security/runtime references and affected frontend/manager READMEs in present tense, remove obsolete parallel-entry descriptions, and update the existing migration guidance. Verify `make -C docs/architecture generate` and `make -C docs/architecture check`.
- [x] 3.2 Reconcile these artifacts with the implementation, validate strictly, sync/archive the completed change, and create one clean implementation commit on `chore/rust-rebac` with no unrelated changes. Verify clean diff/status and report the commit; do not push or reset the deployment.

## Planning review

Independent read-only review of these artifacts against `2f9ef03539e061f06dc99b93339de79ece1b562f`
covered the existing entry, router, layout, admission/account consumers and manager
contract. The pre-admission logout omission was corrected in design, scenario and
task 1.2, then re-reviewed with no remaining actionable findings. Strict OpenSpec
validation passes. Implementation, runtime checks and full-branch audit are excluded.

## Implementation verification

Reviewed base: `457bbe9d39e4d9777e6925990743d850d0987cdf`; reviewed head: this
implementation working tree, committed with this archive. Independent read-only
review covered entry/router, admission, account lifecycle, navigation, generated
manager consumers, membership selection, UI states, desktop/narrow captures and
affected docs. Missing identity fallback and keyboard menu focus were corrected
with regressions and re-reviewed. Documentation corrections distinguish `/me`
Checks from `/me/spaces` Reads and remove obsolete shell descriptions; both were
re-reviewed. No remaining findings in this lot. Historical branch changes,
unchanged backend internals and unmounted product features are excluded.

- Frontend `make test`: 4346 passed, 7 skipped; auxiliary Make checks passed.
- Frontend `npm run build`: passed; existing large-chunk advisory remains.
- Repository `make code-quality`: passed, including frontend tsc, Prettier and ESLint.
- Manager `make test`: 35 unit and 4 OpenAPI tests passed.
- Manager `make test-integration`: 48 passed; `make code-quality`: passed.
- Final `make test-provisioning-browser`: real journey passed in 47.79 seconds,
  then 48 integration tests passed. One import at a time, 15 imported identities,
  one organization, three teams and a project variant. Keyboard logout and
  pending-consent Bob -> root -> Bob prove account isolation. Unsupported URLs
  redirect home and unexpected Python/runtime requests fail the test.
- Screenshots at 1280x900 and 390x844 reviewed; layout, report and membership
  details remain readable. No k3d or developer data was changed.
- An initial browser run stalled during dynamic router loading while sources
  were changing. Two subsequent stable-source runs passed, including the final
  keyboard/account-switch assertions; no permission failure was reproduced.
- Arc42 generate/check and diagram rendering passed. Migration check passed.
  Strict change validation and validation of all 29 main specs passed.

The obsolete Python-only admission guard has no remaining production consumer and
is removed with its superseded tests. The remaining unmounted feature code is not
bulk-deleted. No API, role, SQL migration, infrastructure or compatibility changes.
