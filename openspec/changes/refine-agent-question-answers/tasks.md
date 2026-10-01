## 1. Runtime behavior

- [x] 1.1 Make questions with two to four choices persist `free_text=true` even when the tool argument is false; verify focused question-tool and resume tests, including the unchanged four-choice rejection.
- [x] 1.2 Suppress the final answer after a ReAct human interrupt while retaining failed-tool trace events; verify a focused failed-call-then-pause regression and ordinary failed-turn tests.

- [x] 1.3 Preserve pre-pause sources, UI parts, and token usage in the pause event and persisted history; verify the resumed exchange retains them without a stale final answer.

- [x] 1.4 Recover marked Mistral `ask_user` calls whose JSON question contains literal line breaks after HITL resume. Validate the public and full question schemas, retain other rejection guards, and verify ReAct and Deep routing.

## 2. Managed chat

- [x] 2.1 Render the localized text input as the final choice row for agent questions with choices and free text; verify choice, text-only, choice-plus-comment, approval, and length-limit behavior in focused component tests.
- [x] 2.2 Update the compact runtime and UX docs and add the required migration note; verify the docs match the shipped behavior and the migration check passes.

## 3. Close-out

- [x] 3.1 Run targeted tests, full module suites, the root quality gate, and OpenSpec validation and sync; verify draft PR #2900 records the result and limitations. Evidence: runtime 1,729 passed; frontend 3,168 passed; root quality and migration checks passed.
- [x] 3.2 Obtain independent correctness review and resolve its actionable findings.
- [ ] 3.3 Archive the change after merge.
