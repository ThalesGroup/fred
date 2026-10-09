## 1. Scope confirmation

- [ ] 1.1 Obtain developer confirmation of the proposal, design, and delta acceptance criteria before changing application code; record confirmation in the existing PR or task response.

## 2. Capability preparation tools

- [ ] 2.1 Add `begin_document_generation(title)` to writable-document middleware and update new/revised document instructions; verify its small schema, absence of store writes/parts, existing document-ID revision behavior, and direct `write_document` calls with focused writable-document tests.
- [ ] 2.2 Add `begin_html_artifact_generation(title)` to HTML-artifact middleware and update new/revised artifact instructions; verify no preview part is published during preparation and existing artifact-ID, size-limit, and direct-render behavior with focused HTML-artifact tests.
- [ ] 2.3 Add `begin_ppt_generation(title)` under the existing configured fill-tool gate and update instructions while preserving document grounding; verify configured/unconfigured availability, no asset/workspace writes during preparation, dynamic fill schema and optional image tools with `test_fill.py`.
- [ ] 2.4 Require each preparation result before payload composition in the next model round and keep all tool names distinct; verify instruction overlays, tools-by-name consumers, and combined capability activation in focused capability tests.

## 3. Visible composition and publication

- [ ] 3.1 Derive composition activity from successful preparation and publication traces per live exchange/execution in frontend trace utilities; extend `traceUtils.test.ts` to cover no-reasoning waits, repeated preparation, multiple pending kinds, unrelated tools, errors, and publication calls without a marker.
- [ ] 3.2 Show localized composition and publication labels in `ThoughtTrace` using the current turn lifecycle, with pause/error/tool precedence and completed preparation rows; extend `ThoughtTrace.test.tsx` to verify the rendered interval, publication transition, French/English labels, and terminal states.
- [ ] 3.3 Prevent activity from leaking across exchanges, executions, cancelled turns, reloaded history, and the transient new-turn transition; verify the affected `AssistantTurn` and `toThreadMessages` consumers with their existing component/utility tests.

## 4. Integration verification and review

- [ ] 4.1 Add a deterministic ReAct stream test with preparation and publication in separate rounds and no reasoning text; verify preparation call/result precede publication and existing turn/tool budgets still apply, including the additional call near the configured limit.
- [ ] 4.2 Manually validate long document, configured PPT, and HTML generation plus a document/artifact revision on real configured ReAct agents; record visible stage order, representative extra model-round latency/usage, and any unavailable model/environment coverage in the PR. Preparation/publication in one batch does not pass.
- [ ] 4.3 Run affected capability, frontend, and ReAct tests and one repository-root `make code-quality` at the final implementation commit/push stage; record exact commands/results and resolve failures before claiming readiness.
- [ ] 4.4 Apply `audit-branch` against the PR's actual base, obtain independent read-only review, and run `fred-performance-reviewer` for changed tool/model paths; record reviewed base/head, scope, findings/dispositions, verification, and exclusions in the PR.

## 5. Documentation and close-out

- [ ] 5.1 Update the three package READMEs and `docs/swift/ux/COMPONENT-UX.md` for the preparation/composition/publication workflow; verify they describe implemented behavior and link the durable spec without duplicating requirements.
- [ ] 5.2 Reconcile these artifacts with the verified implementation and approved scope, sync the delta spec, and archive the completed change through the repository procedures; verify OpenSpec validation and that no implementation tasks remain, then push the completed implementation to the draft PR linked to the issue.
