Prerequisite: `enforce-single-organization-context` shipped unique server-resolved
organization context. This change covers personal navigation and creation eligibility only.

## 0. Personal-space eligibility design

- [x] 0.1 Specify explicit personal-space creation eligibility in OpenFGA, its authorized grant/revoke actors and bundle representation. Complete entitlement and context request budgets before implementing the personal command; distinguish creation eligibility from existing-space read permission.

## 1. Manager contract and authorization

- [x] 1.1 Extend the existing personal-space command with explicit creation eligibility, 201 creation and 200 current-authority reuse; verify HTTP responses, sequential/repeated opens and two concurrent opens returning one committed UUID. Preserve I4, I6 and I20 and cite proved invariants in tests.
- [x] 1.2 Add regressions for editor-only revocation, full personal read revocation, organization access revocation while waiting, another user's space, governance-only access and dependency failures; verify zero grant writes on reuse/refusal and no replacement space.
- [x] 1.3 Add organization_id to membership responses from existing canonical placement and regenerate OpenAPI/RTK; verify two people in distinct organizations, isolated personal UUIDs, unchanged personal paths and generated response shapes.
- [x] 1.4 Assert the completed design's exact Check/Read/Write budgets and pagination for absent/existing personal spaces including organization context and explicit creation eligibility; record fixture cardinalities and concurrency in these tasks.

- [x] 1.5 Implement and test exact additive model publication, readonly load refusal, concurrent initialization and failed SQL publication without data reset.

## 2. Existing navigation wiring

- [x] 2.1 Connect the existing personal-space entry and server-resolved unique-organization context to generated manager data, retaining shared components/styles and collective-space navigation; verify unique attachment, rejected multiple attachments, invalid selection and platform-only root without a new selector or creation button.
- [x] 2.2 Wire personal-entry activation, pending/error handling and membership refresh to the generated mutation; verify repeated entry, editor revocation, delayed completion after account changes, reload and the absence of role adapters or synthetic personal identifiers.
- [x] 2.3 Extend the existing real-OIDC browser journey with Priya's personal entry and fredlab selection, account isolation and access refusals; assert no control-plane/knowledge-flow/runtime requests and capture the existing layout at wide and narrow widths. Keep Resources and unrelated consumers unmounted.

## 3. Review, documentation and local completion

- [x] 3.1 Run manager make test, make test-integration and make code-quality; run affected frontend tests/typecheck, root code-quality and the browser acceptance; record exact commands/results here, including any environment limitation rather than claiming a pass.
- [x] 3.2 Apply audit-branch to the full branch against its actual target and obtain an independent read-only review of the lot and consumers; fix actionable findings with regressions and have corrections rereviewed. Record base/head, coverage and dispositions here.
- [x] 3.3 After review, update arc42 chapters 2, 3, 4 and 9 and affected A1-A3 references with implemented behavior and measured request budgets; add the migration note, regenerate derived blocks, and pass make -C docs/architecture check and migration validation.
- [x] 3.4 Reconcile this change, validate strictly, sync/archive using the repository procedures and make one clean local implementation commit under #3092. Verify the commit excludes unrelated files; do not push.

## Verification and review evidence

- Generated contracts: `make -C apps/frontend update-fred-manager-api`.
- Offline manager: `make -C apps/fred-manager test`, 36 unit + 5 OpenAPI tests pass.
- Frontend focused Vitest: HomeNavPanel, HomePage and fredManagerApi, 23 tests pass.
  Includes delayed account change, delayed/failed/stale membership refresh and no 401 replay.
- Full root `make code-quality` and manager `make code-quality` pass. Initial
  formatting failures were corrected before the passing runs.
- Arc42: generated blocks regenerated; `make -C docs/architecture check` passes,
  including ER regeneration and Mermaid rendering. Migration declaration validates.
- Request fixtures: three members, two then three personal spaces, forced FGA page
  size 1: creation 2 Checks/5 Reads/1 Write(5 operations); reuse 2/9/0. Separate
  one-org/two-person grant fixture: 1 Check/5 Reads/1 Write. Concurrent opening: 2.
  Demo: 15 users, 28 space grants, 4 platform grants: 28 Checks/44 Reads/24 Writes,
  91 tuple operations. These are RPC counts, not throughput measurements.
- Independent backend and frontend reviews against `1ccb4796258749f57dbb6c85f1659784ac17bed5`
  plus local changes. Full branch audit refreshed against actual Swift merge base
  `e44837560a2b45df2e23802cd8c067097d5cf00d`, reusing prior review of unchanged areas.
  Coverage: context/authorization, provisioning/CLI, FGA publication, API/generated
  consumers, mounted navigation, arc42/migration. Unchanged bootstrap, consent,
  storage, dispatch and deployment covered by preceding full-branch audit. Archives,
  lockfiles and historical Swift merge internals not reread in full; no load campaign.
- Closed findings: eligibility now publishes after content across batch boundaries
  (96-user existing-org failure/replay regression); selection waits for refreshed
  memberships and verifies the UUID (slow/failing/stale query regressions); README
  now documents exact additive upgrade instead of default reset. Corrections independently
  rereviewed with no outstanding findings. Lock-wait test establishes an actual
  advisory waiter before revocation.
- Dedicated arc42 pass follows implementation review. No applied SQL migration edited,
  no data reset, no push of this new lot. The preceding organization commit was pushed
  as explicitly requested.
- Final real OIDC browser and integration run: `make -C apps/fred-manager test-browser`
  passes 1 browser + 70 integration tests. Initial post-refresh browser test reloaded
  before awaited navigation; it now waits for the resulting URL before reload.
  Screenshots at 1280x900 and 390x844 inspected in ignored frontend target directory.
- Final independent rereview closes all findings; no outstanding implementation or
  documentation finding. OpenSpec strictly validated, synchronized and archived.
