Linked issue: #2987 (first slice). Ships inside the ppt_builder PR (#2679).

## 1. SDK and runtime

- [x] 1.1 Add non-abstract `CapabilityTeamAuthorizer.require_capability_manager()` (default 403) in fred-sdk; verify with an SDK contract test that an implementer without it raises 403.
- [x] 1.2 Implement it in `RebacCapabilityTeamAuthorizer` as an organisation `CAN_MANAGE_CAPABILITIES` check, with the same enforce/disabled rules as `require_agent_editor`; verify with runtime tests covering allowed, denied, ReBAC disabled and no user.
- [x] 1.3 Add the `capability_platform_model` route dependency (fred-sdk) and bind one pod-wide teamless `RoutedCapabilityModelPort` in fred-runtime; verify with a test that a route receives a port without a team.
- [x] 1.4 Add dated `RUNTIME-EXECUTION-CONTRACT.md` §8 entries for 1.1 and 1.3, and update `AUTHORING.md` and the `add-fred-capability` skill.

## 2. Capability storage and routes

- [x] 2.1 Add the Alembic revision (nullable `template_filename`) on the current capability head; verify a single head and a real upgrade/downgrade.
- [x] 2.2 Add `AnalysisStore.delete`, `template_filename` and the reserved platform id; verify with store tests.
- [x] 2.3 Add the `/platform*` routes (D2), with manager-only writes carrying the vision choice, and guard `/analysis/{id}` against the reserved id; verify with route tests (403 for non-managers, Fred template when unset, upload/re-run/reset happy paths, invalid upload keeps the previous default, agent rows untouched by a re-run).

- [x] 2.4 Keep the previous platform template while a replacement is analysed or failed: uploads and re-runs analyse the `__platform_next__` row, promoted onto `__platform__` in `finish`'s transaction on success; reset deletes both; `GET /platform` reports both and restarts an interrupted replacement (D1, D2); verify with route and job tests (pending and failed replacements keep the previous template for agents, success promotes it, a re-run keeps the current one in use, reset clears both).
- [x] 2.5 Store the manager's pattern edits on the platform row (`overrides_json`, amended into `r9d3f4a5b6c7`, never applied) with `PUT /platform/overrides`, pruned against the template in effect; a promotion keeps them pruned for the same file and drops them for another (D7); verify with route tests (manager-only, pruning, kept on re-run, dropped on a new file, applied to agents through the snapshot), a single head and a real SQLite upgrade/downgrade/check.
- [x] 2.6 Let the manager edit the Fred template's slides when no platform template is in effect: `PUT /platform/overrides` stores them, pruned against the shipped inventory, in a reserved `__builtin__` row (no schema change), `GET /platform` returns them as `overrides`, reset deletes them, and the snapshot applies them (D7); verify with route and resolution tests (manager-only, pruning, applied to agents from the snapshot, unused under an uploaded template, cleared by reset, the agent routes reject the reserved id).

## 3. Resolution

- [x] 3.1 Add the pod-local platform snapshot (30 s TTL, background refresh once expired, writer invalidation); verify with tests for TTL refresh, invalidation, and no DB read on a fresh snapshot.
- [x] 3.2 Middleware `template_sha256 is None`: platform default when its analysis succeeded, else built-in; verify with tests for pending, failed and succeeded platform analyses, the agent template winning, and readiness never failed by the platform row.
- [x] 3.3 `validate_config` drops overrides when `template_sha256 is None`, and the middleware ignores stored ones (D7); verify with a test that an agent returning to no template builds unedited.

## 4. Control plane

- [x] 4.1 Add `route_base_url` to `CapabilityEnablementItem` and the team-free `GET /routing-policy/available-models` (D8); verify with control-plane tests, then regenerate `openapi.json` and `controlPlaneOpenApi.ts`.
- [x] 4.2 Add a dated `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry for 4.1.

## 5. Frontend

- [x] 5.1 Regenerate the ppt_builder client and verify the `/platform*` hooks exist.
- [x] 5.2 Add `platformPanel` to `CapabilityUiPlugin` plus a `platformPanelFor` registry; FeaturesPage shows the settings action only when a panel exists and dispatches capability base URLs; verify with FeaturesPage tests (action shown for ppt_builder, hidden otherwise).
- [x] 5.3 Build the platform drawer: current template, upload, status (the previous template stays in use while a replacement is pending or failed), vision choice, re-run, patterns PDF, "Review the slides" (editable for managers, saved as the platform's pattern edits), reset behind a `ConfirmationDialog`; writes shown to capability managers only; verify with drawer tests (states, permission gating, reset confirmation, the error on an invalid upload).
- [x] 5.4 Agent form: the no-template branch reads `/platform` and shows "Template set by the administrator" with the file name plus the platform slides in the read-only review; upload still overrides it; verify with tests for set and unset defaults.
- [x] 5.5 Add fr/en i18n keys; verify `tsc` and the i18n key checks pass.
- [x] 5.6 Drawer: "Review the slides" on the Fred template too (built-in previews), reset offered when only its edits exist; the agent form applies them in its read-only review; verify with drawer and `usePptBuilderAnalysis` tests.

## 6. Docs and close-out

- [x] 6.1 Update the Help Center fr/en (`features/administration.md` admin side, `features/capabilities.md` fallback order) and verify the pages render.
- [x] 6.2 Update the #2679 migration note (operations: optional activation, capability table column, overrides dropped with no own template).
- [x] 6.3 Run `make code-quality` and `make test` in each touched project, then the `fred-performance-reviewer` skill (middleware per-turn path); record the evidence in `verification.md`.
- [ ] 6.4 Browser check: upload a platform template as admin, see it in an agent form without a template, build a deck on it, reset to the Fred template; record it in `verification.md`.
