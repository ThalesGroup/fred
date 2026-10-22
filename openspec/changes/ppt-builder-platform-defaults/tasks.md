Linked issue: #2987 (first slice). Ships inside the ppt_builder PR (#2679).

## 1. SDK and runtime

- [ ] 1.1 Add non-abstract `CapabilityTeamAuthorizer.require_capability_manager()` (default 403) in fred-sdk; verify with an SDK contract test that an implementer without it raises 403.
- [ ] 1.2 Implement it in `RebacCapabilityTeamAuthorizer` as an organisation `CAN_MANAGE_CAPABILITIES` check, with the same enforce/disabled rules as `require_agent_editor`; verify with runtime tests covering allowed, denied, ReBAC disabled and no user.
- [ ] 1.3 Add the `capability_platform_model` route dependency (fred-sdk) and bind one pod-wide teamless `RoutedCapabilityModelPort` in fred-runtime; verify with a test that a route receives a port without a team.
- [ ] 1.4 Add dated `RUNTIME-EXECUTION-CONTRACT.md` §8 entries for 1.1 and 1.3, and update `AUTHORING.md` and the `add-fred-capability` skill.

## 2. Capability storage and routes

- [ ] 2.1 Add the Alembic revision (nullable `template_filename`) on the current capability head; verify a single head and a real upgrade/downgrade.
- [ ] 2.2 Add `AnalysisStore.delete`, `template_filename` and the reserved platform id; verify with store tests.
- [ ] 2.3 Add the `/platform*` routes (D2), with manager-only writes carrying the vision choice, and guard `/analysis/{id}` against the reserved id; verify with route tests (403 for non-managers, Fred template when unset, upload/re-run/reset happy paths, invalid upload keeps the previous default, agent rows untouched by a re-run).

## 3. Resolution

- [ ] 3.1 Add the pod-local platform snapshot (30 s TTL, background refresh once expired, writer invalidation); verify with tests for TTL refresh, invalidation, and no DB read on a fresh snapshot.
- [ ] 3.2 Middleware `template_sha256 is None`: platform default when its analysis succeeded, else built-in; verify with tests for pending, failed and succeeded platform analyses, the agent template winning, and readiness never failed by the platform row.
- [ ] 3.3 `validate_config` drops overrides when `template_sha256 is None`, and the middleware ignores stored ones (D7); verify with a test that an agent returning to no template builds unedited.

## 4. Control plane

- [ ] 4.1 Add `route_base_url` and `vision_profile_ids` to `CapabilityEnablementItem`; verify with control-plane tests, then regenerate `openapi.json` and `controlPlaneOpenApi.ts`.
- [ ] 4.2 Add a dated `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry for 4.1.

## 5. Frontend

- [ ] 5.1 Regenerate the ppt_builder client and verify the `/platform*` hooks exist.
- [ ] 5.2 Add `platformPanel` to `CapabilityUiPlugin` plus a `platformPanelFor` registry; FeaturesPage shows the settings action only when a panel exists and dispatches capability base URLs; verify with FeaturesPage tests (action shown for ppt_builder, hidden otherwise).
- [ ] 5.3 Build the platform drawer: upload, status, vision choice, re-run, reset, read-only review; verify with drawer tests, including toasts on upload/reset and the error on an invalid upload.
- [ ] 5.4 Agent form: the no-template branch reads `/platform` and shows "Set by the administrator" (no template name) plus the platform slides in the read-only review; verify with tests for set and unset defaults.
- [ ] 5.5 Add fr/en i18n keys; verify `tsc` and the i18n key checks pass.

## 6. Docs and close-out

- [ ] 6.1 Update the Help Center fr/en (`features/capabilities.md` admin side, `agents.md` agent form line) and verify the pages render.
- [ ] 6.2 Update the #2679 migration note (operations: optional activation, capability table column, overrides dropped with no own template).
- [ ] 6.3 Run `make code-quality` and `make test` in each touched project, then the `fred-performance-reviewer` skill (middleware per-turn path); record the evidence in `verification.md`.
- [ ] 6.4 Browser check: upload a platform template as admin, see it in an agent form without a template, build a deck on it, reset to the Fred template; record it in `verification.md`.
