## 1. Shared startup catalog

- [ ] 1.1 Add optional directory configuration and the bounded read-only startup snapshot/backend in `libs/fred-runtime`; verify path resolution, absent configuration, UTF-8/size bounds, unreadable files, traversal and escaping symlinks with offline tests.
- [ ] 1.2 Adapt upstream `SkillsMiddleware` public discovery/state hooks, reject duplicate names and carry the catalog through runtime services; verify invalid-entry diagnostics, fixed reads before restart and new metadata/body reads after restart in an existing checkpoint.
- [ ] 1.3 Render escaped skill metadata and Fred loading guidance inside the shared `<tools>` block; verify unchanged no-skills prompt bytes, reserved-tag escaping, no eager body injection and preserved platform precedence for ReAct and Deep.

## 2. Agent loading and continuity

- [ ] 2.1 Implement shared `load_skill` and `read_skill_file` tools through the existing binding/observability path; verify name-based loading, confined references, write/execute rejection, tool-name collisions, attribution and no tool/permission provisioning.
- [ ] 2.2 Wire the same catalog, tools and middleware into ReAct, DeepAgent and explicit Deep-child construction; verify deterministic model doubles can load, read a reference, invoke a task tool and finish, including two skills in one request.
- [ ] 2.3 Preserve loaded content in ordinary checkpoint messages under existing history limits and add scope/missing-tool guidance; verify follow-up/resume retains available instructions, trimming permits reload and no persistent selection is written.

## 3. Typed web invocation and history

- [ ] 3.1 Add typed catalog/invocation/load-attribution contracts and authenticated runtime/product metadata routes using the selected managed instance's runtime source; verify team-use denial, source isolation, unsupported runtime behavior and catalog payloads without bodies/host paths.
- [ ] 3.2 Validate and preload user-selected skills before inference through the common loader; verify a fake model is not called on unavailable selection, forged client bodies are ignored/rejected, and successful instructions enter checkpoint flow before the first model call.
- [ ] 3.3 Project compact user/agent load attribution through streaming and stored history using existing exchange/child identities; verify truthful manual preloads, automatic and child loads, history rehydration and no duplication on HITL/interruption replay.
- [ ] 3.4 Regenerate runtime and control-plane OpenAPI schemas and frontend clients with the repository Make targets; verify typed consumers compile and generated files were not hand-edited.

## 4. Composer and reserved command

- [ ] 4.1 Reserve `skill` in prompt command assignment/import, keep legacy prompts library-accessible and allow renaming; verify create/update/import conflicts, preservation of existing legacy data and unaffected other prompt commands.
- [ ] 4.2 Extend the existing composer hook/menu for `/skill <name> <request>`, fetching the actual selected runtime catalog; verify prefix filtering, Tab/Enter/arrows/Escape, bare-prefix guidance, missing request, resolve errors and stale-response handling after agent/team switches.
- [ ] 4.3 Render localized compact skill-load steps with origin in live and reopened chat; verify manual/automatic/child attribution and add English/French labels and Help Center guidance for invocation and legacy command renaming.

## 5. Distribution and acceptance example

- [ ] 5.1 Add `compte-rendu/SKILL.md` and `references/modele-compte-rendu.md` under the platform skill directory, then include them in `apps/fred-agents` distribution; verify upstream discovery accepts the files and the referenced template resolves from the deployed path.
- [ ] 5.2 Update pod configuration examples, chart values/templates and regenerated schemas for optional read-only activation; verify chart rendering/schema validation and that unconfigured deployments retain existing behavior.
- [ ] 5.3 Manually validate web invocation and ordinary-request automatic selection with notes containing a decision/action but no deadline, plus a missing-reader case; record actual behavior and any model-following limitation in this checklist or the implementation PR.

## 6. Verification and close-out

- [ ] 6.1 Update runtime/product prompt and execution contracts, existing prompt guidance and an English operator migration note covering activation, restart, replica consistency, `/skill` reservation and rollback; verify each changed public boundary has one authoritative documented home and the migration guide declares the appropriate operational impact.
- [ ] 6.2 Run affected offline test suites, raw `basedpyright` where a non-empty baseline exists, and `make code-quality` from the monorepo root; record exact commands/results and fix relevant failures before readiness.
- [ ] 6.3 Apply `audit-branch` to the full implementation against its actual target and obtain independent read-only review plus `fred-performance-reviewer` for startup/model/tool paths; record base/head, coverage, findings/dispositions and exclusions in the PR or this task response.
- [ ] 6.4 Reconcile these artifacts with the verified implementation, validate/sync/archive using the repository OpenSpec procedures and push a draft implementation PR linked to #2711; verify the archived capability is current and no unchecked required task remains before declaring implementation complete.
