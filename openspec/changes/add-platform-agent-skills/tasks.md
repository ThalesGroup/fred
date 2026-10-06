## 1. Shared startup catalog

- [x] 1.1 Add optional directory configuration and the bounded read-only startup snapshot/backend in `libs/fred-runtime`; verify installed-package and configured-relative path resolution, absent configuration, UTF-8/size bounds, unreadable files, traversal and escaping symlinks with offline tests.
- [x] 1.2 Adapt upstream `SkillsMiddleware` public discovery/state hooks, reject duplicate names and carry the catalog through runtime services; verify invalid-entry diagnostics, fixed reads before restart and new metadata/body reads after restart in an existing checkpoint.
- [x] 1.3 Render escaped skill metadata and Fred loading guidance inside the shared `<tools>` block; verify unchanged no-skills prompt bytes, reserved-tag escaping, no eager body injection and preserved platform precedence for ReAct and Deep.

## 2. Agent loading and continuity

- [x] 2.1 Implement shared `load_skill` and `read_skill_file` tools through the existing binding/observability path; verify name-based loading, confined references, write/execute rejection, tool-name collisions, attribution and no tool/permission provisioning.
- [x] 2.2 Wire the same catalog, tools and middleware into ReAct, DeepAgent and explicit Deep-child construction; verify deterministic model doubles can load, read a reference, invoke a task tool and finish, including two skills in one request.
- [x] 2.3 Preserve loaded content in ordinary checkpoint messages under existing history limits and add scope/missing-tool guidance; verify follow-up/resume retains available instructions, trimming permits reload and no persistent selection is written.

## 3. Typed web invocation and history

- [x] 3.1 Add typed catalog/invocation/load-attribution contracts and authenticated runtime/product metadata routes using the selected managed instance's runtime source; verify team-use denial, source isolation, unsupported runtime behavior and catalog payloads without bodies/host paths.
- [x] 3.2 Validate and preload user-selected skills before inference through the common loader; verify a fake model is not called on unavailable selection, forged client bodies are ignored/rejected, and successful instructions enter checkpoint flow before the first model call.
- [x] 3.3 Project compact user/agent load attribution through streaming and stored history using existing exchange/child identities; verify truthful manual preloads, automatic and child loads, history rehydration and no duplication on HITL/interruption replay.
- [x] 3.4 Regenerate runtime and control-plane OpenAPI schemas and frontend clients with the repository Make targets; verify typed consumers compile and generated files were not hand-edited.

## 4. Composer and reserved command

- [x] 4.1 Reserve `skill` in prompt command assignment/import, keep legacy prompts library-accessible and allow renaming; verify create/update/import conflicts, preservation of existing legacy data and unaffected other prompt commands.
- [x] 4.2 Extend the existing composer hook/menu for `/skill <name> <request>`, fetching the actual selected runtime catalog; verify prefix filtering, Tab/Enter/arrows/Escape, bare-prefix guidance, missing request, resolve errors and stale-response handling after agent/team switches.
- [x] 4.3 Render localized compact skill-load steps with origin in live and reopened chat; verify manual/automatic/child attribution and add English/French labels and Help Center guidance for invocation and legacy command renaming.

## 5. Distribution and acceptance example

- [x] 5.1 Add `compte-rendu/SKILL.md` and `references/modele-compte-rendu.md` under `libs/fred-runtime/fred_runtime/skills/`, declare the required package data and verify both wheel/source-distribution inclusion and upstream discovery/reference reads from an installed build outside the checkout; no application-owned copy is required.
- [x] 5.2 Update pod configuration examples, chart values/templates and regenerated schemas for optional read-only activation; verify chart rendering/schema validation, that `apps/fred-agents` images consume the runtime-packaged skills, and that unconfigured deployments retain existing behavior.
- [ ] 5.3 Manually validate web invocation and ordinary-request automatic selection with notes containing a decision/action but no deadline, plus a missing-reader case; record actual behavior and any model-following limitation in this checklist or the implementation PR.

## 6. Verification and close-out

- [x] 6.1 Update runtime/product prompt and execution contracts, existing prompt guidance and an English operator migration note covering activation, restart, replica consistency, `/skill` reservation and rollback; verify each changed public boundary has one authoritative documented home and the migration guide declares the appropriate operational impact.
- [x] 6.2 Run affected offline test suites, raw `basedpyright` where a non-empty baseline exists, and `make code-quality` from the monorepo root; record exact commands/results and fix relevant failures before readiness.
- [x] 6.3 Apply `audit-branch` to the full implementation against its actual target and obtain independent read-only review plus `fred-performance-reviewer` for startup/model/tool paths; record base/head, coverage, findings/dispositions and exclusions in the PR or this task response.
- [ ] 6.4 Reconcile these artifacts with the verified implementation, validate/sync/archive using the repository OpenSpec procedures and push a draft implementation PR linked to #2711; verify the archived capability is current and no unchecked required task remains before declaring implementation complete.


## Verification evidence

- Runtime: `libs/fred-runtime/.venv/bin/pytest libs/fred-runtime/tests -q --disable-warnings` — 1825 passed, 16 skipped (documented integration prerequisites), 1 warning. Initial complete-suite failures were stale doubles missing optional `skill`/`skills`; corrected and complete suite rerun. Metadata-route tests exposed and fixed the reused request's required-input validation.
- SDK: `libs/fred-sdk/.venv/bin/pytest libs/fred-sdk/tests -q --disable-warnings` — 504 passed, 3 skipped (unrepresentable URL/Literal cases).
- Control plane: affected catalog, product authorization and marketplace suites — 33 passed. Frontend final affected compose/history/trace/prompt/import suites — 332 passed. TypeScript compiles.
- Raw `.venv/bin/basedpyright --outputjson` from each touched Python package: SDK 0 errors/0 warnings; control plane 0 errors/0 warnings; runtime 0 errors/7 existing warnings. Root `make code-quality` passed with the installed uv binary on PATH.
- Wheel and sdist built with `uv build`; both include `compte-rendu/SKILL.md` and its reference. Extracted wheel imported from `/tmp/platform-skills-final-installed` while working outside the checkout; upstream discovery and reference reads passed.
- `helm lint deploy/charts/fred`, `helm template ... --set applications.fred-agents.configuration.skills.directory=package` and `make migration-check MIGRATION_BASE=82444dc9fc2785cfc8c8e87ad6d4c6771caf894e` passed. Runtime/CP clients generated with frontend `make update-runtime-api update-control-plane-api`.
- Independent runtime/performance review and CP/UI review against base `82444dc9fc2785cfc8c8e87ad6d4c6771caf894e` through implementation HEAD `2727a2eb963a55264625905bf20ff7c6714705b0`: recursive YAML and symlink-loop isolation, safe ancestor opening, diagnosable folder labels, catalog request validation, import localization and contract error descriptions corrected with regression coverage. No hot-path filesystem/network-sink I/O added; existing model/tool observability retained. Live concurrency campaign excluded: no demonstrated performance hazard required one.
- Live web/model acceptance remains pending: running APIs have no reload flag and require coordinated restart; both available browsers displayed the login page. Restart confirmation and user sign-in requested; no service was restarted and no real-model success is claimed.
