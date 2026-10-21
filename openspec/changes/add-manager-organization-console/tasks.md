## 1. Manager governance contract

- [x] 1.1 Add bounded owner-only organization registry and creation with separate known owner/admin identities, reusing guarded publication; verify focused HTTP integration cases for admission/authority, distinct/same identity, duplicate names, unknown/conflicting identity, pagination/retirement and revoked waiting creator.
- [x] 1.2 Regenerate OpenAPI and the manager frontend client; verify the generated contract and focused FGA request-budget assertions without changing the model or schema.

## 2. Existing administration UI

- [x] 2.1 Add Organizations beside Provisioning with the team-administration components/styles, paginated list and name/owner/admin form; verify loading/error/empty, creation, duplicate submission and late completion with focused component tests.
- [x] 2.2 Restrict the owner's platform area and landing to organization governance/provisioning/account routes, preserving the ordinary business UI; verify mixed-role owner routing, direct URLs, skipped business consumers and ordinary-user route retention with focused tests and TypeScript.

## 3. Review and delivery

- [x] 3.1 Obtain independent read-only patch review, fix actionable findings and re-review corrections; record reviewed base/head, coverage and targeted verification, excluding the deferred full campaign.
- [x] 3.2 Update arc42 journeys, organization/runtime and request costs with implemented behavior; validate/sync the delta spec, inspect the scoped diff and commit locally. Record deployment status explicitly, without pushing absent agreement.

- [x] 3.3 Record the developer's deployed manual validation of the organization console.
- [ ] 3.4 Complete the agreed deferred browser/global campaign; archive after these validations. No deployment or push is performed by this lot.

## Verification and review evidence

- Scope confirmed in the developer conversation: preserve the complete business UI; add Organizations beside Provisioning only in the platform area; create an organization with selected existing owner/admin accounts. The separate entry into an owner's organization remains out of scope. Issue #3092, branch `chore/rust-rebac`, implementation base `4510d2a95`.
- `make -C apps/control-plane test-integration CARGO_TEST_OPTS='organization_console'`: 3 passed, 85 filtered, disposable SQL/FGA/identity fixtures. Covers exact targets, no implicit content, authority/admission, attachment/name conflicts, faults before/after publication, retirement/cursor and concurrency 2. Empty-target creation measured 2 Checks, 4 Reads and 2 Writes; registry measured 1 Check per page (102 rows, 101 active).
- `make -C apps/control-plane test CARGO_TEST_OPTS='--test openapi'`: 6 passed, including registered routes and the registry's query-error media type. Manager OpenAPI and frontend client regenerated with `make -C apps/frontend update-control-plane-api`.
- Focused frontend run: 31 tests passed across OrganizationsPage, ManagerArea, router, Onboarding and UserProfile. After review corrections, 9 ManagerArea tests passed; the final two-file rerun passed 16 ManagerArea/UserProfile tests, including pending authority retry and cached business-avatar removal. `tsc --noEmit` passed. Targeted formatting and `node --check apps/frontend/tests/provisioning-browser.mjs` passed; the browser recipe was adapted but not executed.
- Independent read-only review against `4510d2a95`: governance endpoints/publication and current authority, registry bounds, role/CLI compatibility, platform routing/navigation and ordinary consumers. P1: background authority refresh unmounted drafts; corrected to preserve mounted state during successful refresh, with stateful owner/member regressions. P2: pending retry reexposed cached authority; corrected to retain error gating until fulfillment, with a valid/error/pending/success regression. Both corrections were independently re-reviewed without remaining findings in that boundary. Final delta review also covered cached avatar/patch-dialog suppression, query-error OpenAPI, browser recipe and arc42/migration/specs; no additional actionable finding. This is a focused lot review, not a full branch/PR audit.
- Arc42 journeys, organization/runtime contracts, generated route/proof blocks and measured costs updated. `python3 docs/architecture/tools/docs.py generate` and `check`, both affected change validations, and `openspec validate --specs` passed (33 specifications). Current capability spec synchronized; the earlier still-active account delta reconciled to avoid reintroducing the superseded owner landing.
- Per the developer's explicit instruction, no complete test, integration, root-quality, diagram or browser campaign is repeated. On 2026-10-18 the developer reported the deployed lot tested and apparently successful before starting the folder journey. This records manual acceptance, not execution of the deferred automated campaign. Existing imports, schema and FGA model are unchanged. This lot is committed locally without push.
