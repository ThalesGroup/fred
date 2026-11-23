# Tasks

## 1. Tracking and geo foundation

- [x] 1.1 Confirm the issue/Epic choice, create or reuse the chart tracking issue before implementation, and verify its scope matches this change.
- [x] 1.2 After the geo worktree is clean, add the generic local handler and optional output part declaration to the SDK built-in catalog in the geo branch, move geo conversion into that path, and verify its focused SDK and runtime tests pass without an application invoker.
- [x] 1.3 Rebase this chart branch onto the geo refactor, document the native authoring path in `libs/fred-sdk/README.md`, and verify the chart diff excludes the geo branch's prior commits and uncommitted work.

## 2. Chart contract and runtime delivery

- [x] 2.1 Add the bounded chart argument model, `ChartPart`, and pure chart handler to the shared built-in declaration; verify focused SDK tests cover valid views, numeric strings/nulls, invalid mappings, pie values, row and character limits, and no partial output.
- [x] 2.2 Register built-in output parts through the existing boot-time union rebuild, document the boot contract in `RUNTIME-EXECUTION-CONTRACT.md`, and verify registry tests cover chart availability, geo deduplication, and kind collisions.
- [x] 2.3 Expose chart once in ReAct, Deep, and Graph through the shared local execution path, carry its part into final and awaiting-human events, and verify targeted resolver, Graph pause/resume, and tool-event tests pass.
- [x] 2.4 Regenerate runtime OpenAPI with `make update-runtime-api` and verify the generated client includes `ChartPart` without a handwritten type.

## 3. Chat and SQL experience

- [x] 3.1 Add the Recharts chart part renderer, token-based styles, localized labels, and a semantic raw-row table; verify focused frontend tests cover all views, long labels, malformed saved parts, and light/dark rendering.
- [x] 3.2 Extend the packaged tabular prompt and a no-LLM reference scenario to call the shared chart tool with returned rows; verify the focused agent and chat-part transport tests pass without an external SQL service.
- [x] 3.3 Update `COMPONENT-UX.md` for the new chat part and add the required `impact: none` migration note; verify the note with `make migration-check`.

## 4. Integration and review

- [x] 4.1 Run the affected offline suites and one root `make code-quality`, perform the required performance and full branch reviews against the actual target branch, obtain an independent read-only review, and record test results and finding dispositions in the PR.
- [x] 4.2 Reconcile the spec and design with the implementation, open the chart draft PR against the geo branch, and verify its diff contains only chart work and the reviewed shared contract.

## Workflow follow-up

- Sync the delta spec and archive this change after implementation, verification, and review.
