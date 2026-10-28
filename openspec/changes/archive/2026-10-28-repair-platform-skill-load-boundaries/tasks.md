## 1. Reproduce and repair

- [x] 1.1 Add a real compiled native overflow test proving one physical read produces one load event and usage count across recovery; observe red then green after the invocation-scoped observation fix.
- [x] 1.2 Reproduce capability read/concat through an alias to an ineligible skill; enforce resolved-target rules and verify agent/system denial plus permitted aliases and ordinary filesystem behavior.
- [x] 1.3 Reproduce agent-only preview denial and the composer history crash during a rejected stale selection; restore authorized preview and document-aligned history, then replay the rejection in the browser.

## 2. Integrate and verify

- [x] 2.1 Run the skills and filesystem regression suites, including concurrency, children, resume, usage and trace inputs, and record results here.
- [x] 2.2 Complete the user-facing acceptance matrix in the UI: FR/EN, explicit/implicit selection, preview, admin opt-out/recovery, history/reload and truthful trace input.
- [x] 2.3 Obtain independent read-only correctness and runtime performance review; resolve supported findings and pass root code quality plus affected module suites.
- [x] 2.4 Reconcile current specs and compact docs, archive this change, and keep all commits local with the model stash preserved.

Task 1.1 evidence: both real overflow cases failed before the fix; 93 targeted
recovery, policy, pin, concurrency, HITL and stream tests pass after it. Provider
failure and a separately compiled follow-up preserve checkpointed instructions
without another physical read or usage count. Scoped typing and Ruff pass.

Task 1.2 evidence: three real capability alias/concat cases failed before the
fix; 54 filesystem, native-parity, concat and internal-consumer tests pass after
it. Agent/system denial, ordered rules and permitted aliases are covered.
Scoped typing has no errors; one pre-existing unreachable warning remains.

Task 1.3 evidence: preview regression failed before the API fix, then all 79
platform-skill cases passed. Two real editor composition cases reproduced the
same RangeError before the fix; 186 composer/editor cases now pass. The browser
replay preserves the draft and shows the rejected request without crashing.
An independent counterexample then found loss of a selected prompt's identity
after consecutive edits before React rendered. Three further regressions were
red, then green after publishing current text and choices together. All 189
composer tests and the independent counterexample pass.

Task 2.1 evidence: 2,358 runtime offline tests pass (23 integration tests
deselected). This includes native pins, recovery, fresh graph/checkpoint state,
concurrency, children, resume, permission parity, complete stream persistence,
attribution and trace inputs. Log: /tmp/platform-skills-full-runtime-offline.log.
The integrated frontend suite passes 4,829 tests (8 skipped); control-plane
passes 345 selected tests, SDK 185 (3 skipped), fred-agents 14, table ownership
2, and Helm 19 tests with 24 subtests. Six additional SDK default/roundtrip
invariants pass. No tests require a live external model.

Task 2.2 UI evidence (owned synthetic conversations only):

| Requirement | Observed result |
| --- | --- |
| Defaults and invocation controls | Nine packaged skills enabled; eight user-selectable. Agent-only data-visualization is absent from the menu but can be loaded and previewed. grill-me is user-only. |
| Native pinning and trace | Session 79c0cea0-f6c7-48cf-821b-96f2ac463b12 pins graph then verify-answer before reasoning. Trace 27e779054bc8ae368d96bb327a5ac706 shows root input messages plus both pinned_skills; first provider input has one current request and two native bodies. |
| Visibility and persistence | Exactly two explicit load rows before collapsed reasoning, one user request and one final answer persist after reload; Copy message returns both canonical commands. |
| FR/EN presentation | Menu identifiers have no slash, tooltip is localized title plus description only, preview order is title/description/arguments/body; body and argument hints remain English. Both locales and the accepted grill-me description were inspected. |
| Global policy | Disable persists after admin reload; the disabled skill disappears from a fresh menu. A stale selected draft is rejected without another execution, preserved without a page crash, and can be cleared. Re-enable by keyboard persists. Replayed again after the final hook correction. |
| Agent-only preview | Session e74c33f4-81be-47e2-a287-375aa44fd2c6 has one actual native data-visualization read, agent-origin activity and an authorized preview in both locales. |
| Layout and keyboard | At 1100x650 the admin region has no horizontal overflow. Menu filtering, Escape, Enter, deletion and undo were exercised; composer identity/selection boundaries also have composition regressions. Viewport restored. |
| Catalog and licensing | All 12 supplied Mermaid examples parse with installed Mermaid 11.16.1. All 17 Markdown/text resources match isolated wheel/sdist contents; pinned upstream MIT license and notices are included. grill-me body/method remain unchanged. |

Model follow-through limit: plain diagram requests in French and English did not
trigger a skill read with Mistral Small 4, although independent inspection of
both real provider inputs confirms the catalog, mandatory read instruction and
read_file schema were present, with no prior body. A named natural-language
graph request and agent-only path request do perform real reads. Explicit native
pins reliably preload; spontaneous selection remains model-dependent. This is
recorded as a failing model-follow-through case, not a passing implicit-load
test. No keyword router, extra model call or grill-me procedure change was added.

Full-branch review coverage: merge base d76d96ba0f6642871b2191cedb1ecb32df0b0d2a
against origin/swift through 96246a8b9663e82e1fd84e49c8f9fab83ccbc1e2,
then corrective commits through dcd2a27e9 and final contract documentation.
Independent read-only responsibilities covered runtime/native state and
filesystem consumers, UI/composer/API consumers, catalog/defaults/package and
license contracts. All actionable findings were repaired and independently
rechecked; the runtime performance review found bounded off-loop resolution and
invocation-scoped state, with no new shared process state or client. No live
load campaign or deployed multi-replica rollout was performed. Offline tests,
fresh compiled graphs and shared policy store tests cover the affected state
boundaries; production rollout remains an operator prerequisite.

Close-out: the final root `make code-quality` exits 0 using the existing module
environments (UV_NO_SYNC=1, existing make wrapper), including all Python gates
and frontend TypeScript/Prettier/ESLint. Logs:
/tmp/fred-skills-root-quality-integrated.log and
/tmp/fred-skills-full-frontend-integrated.log. Main spec synchronization is
validated (37 specs pass). The runtime contract reflects preview, retry and
alias rules and distinguishes native explicit pins from model-led selection.
All three core APIs return 200 and both core workers are running. Normal
control-plane configuration, French UI, viewport and enabled graph policy are
restored; composer draft is empty. Optional sample/DT/RAG pods remain offline
and the admin UI truthfully warns about these configured unavailable sources.
Model stash remains 922e8c6aa4937beeb00f2ffc1545e64f67d6cf18; no push or PR.

UI proof files: /tmp/fred-skills-langfuse-pinned-input.png,
/tmp/fred-skills-multiple-pins-final-fr.png,
/tmp/fred-skills-stale-draft-integrated-fr.png,
/tmp/fred-skills-grill-preview-fr.png,
/tmp/fred-skills-agent-only-preview-fr.png and
/tmp/fred-skills-admin-small-window.png. The stale-draft screenshot and the
single persisted user/final pair demonstrate refusal without another execution.
