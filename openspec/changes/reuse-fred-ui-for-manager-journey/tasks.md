## 1. Reuse the existing application

- [ ] 1.1 Restore `App` and the existing router as the sole entry; move manager admission into the existing CGU/bootstrap guards and remove the parallel shell and styles. Verify startup, required/disabled/changed CGU, bootstrap, unavailable state and explicit retries with focused frontend tests.
- [ ] 1.2 Adapt existing providers, layout, rail, admin panel and account menu to the bounded manager journey; remove mounted Python subscriptions and unsupported route destinations. Verify direct URL denial/redirection, manager-only authority, absence of background calls, and identity/logout both before and after admission; test switching accounts from CGU, bootstrap and admission-error screens.
- [ ] 1.3 Adapt the existing home and space list to generated manager memberships and roles, including organization/team/project selection and empty root state. Verify hierarchy, multiple memberships, unchanged role labels, loading/error states and account cache isolation without fake Python DTOs.

## 2. Verify the complete journey

- [ ] 2.1 Extend `make test-provisioning-browser` to traverse the real Fred sidebar, admin console and account menu, retaining all previous consent/bootstrap/import/replay/refusal assertions and project fixture coverage. Verify unsupported direct URLs and reject all unexpected control-plane, knowledge-flow and agent-runtime calls; review desktop and narrow-width screenshots for layout, scrolling and keyboard access.
- [ ] 2.2 Run frontend `make test`, `npm run build`, repository `make code-quality`, and manager `make test`, `make test-integration`, `make code-quality`. Record outcomes and fixture scope here; fix failures without weakening existing business assertions. Mark tests proving existing invariants with `// Proves: I<n>`.
- [ ] 2.3 Apply the branch-review procedure and obtain independent read-only review of the implementation and affected consumers. Record base/head, scope, findings and exclusions here; add a regression test for each actionable defect and obtain review of corrections.

## 3. Reconcile and commit

- [ ] 3.1 After review, update the arc42 journey/security/runtime references and affected frontend/manager READMEs in present tense, remove obsolete parallel-entry descriptions, and update the existing migration guidance. Verify `make -C docs/architecture generate` and `make -C docs/architecture check`.
- [ ] 3.2 Reconcile these artifacts with the implementation, validate strictly, sync/archive the completed change, and create one clean implementation commit on `chore/rust-rebac` with no unrelated changes. Verify clean diff/status and report the commit; do not push or reset the deployment.

## Planning review

Independent read-only review of these artifacts against `2f9ef03539e061f06dc99b93339de79ece1b562f`
covered the existing entry, router, layout, admission/account consumers and manager
contract. The pre-admission logout omission was corrected in design, scenario and
task 1.2, then re-reviewed with no remaining actionable findings. Strict OpenSpec
validation passes. Implementation, runtime checks and full-branch audit are excluded.
