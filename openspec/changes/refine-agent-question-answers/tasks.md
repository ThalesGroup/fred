## 1. Runtime behavior

- [x] 1.1 Make questions with two to four choices persist `free_text=true` even when the tool argument is false; verify focused question-tool and resume tests, including the unchanged four-choice rejection.
- [x] 1.2 Suppress the final answer after a ReAct human interrupt while retaining failed-tool trace events; verify a focused failed-call-then-pause regression and ordinary failed-turn tests.

- [x] 1.3 Preserve pre-pause sources, UI parts, and token usage in the pause event and persisted history; verify the resumed exchange retains them without a stale final answer.

- [x] 1.4 Recover marked Mistral `ask_user` calls whose JSON question contains literal line breaks after HITL resume. Validate the public and full question schemas, retain other rejection guards, and verify ReAct and Deep routing.

- [x] 1.5 Accept an optional short subject title on `ask_user` and persist it on its question request; verify existing title-free calls still work.

- [x] 1.6 Accept one complete batch of pending agent-question answers, validate every occurrence, claim them atomically, resume LangGraph once, and persist one response per call; retain single-answer compatibility.

## 2. Managed chat

- [x] 2.1 Render the localized text input as the final choice row for agent questions with choices and free text; verify choice, text-only, choice-plus-comment, approval, and length-limit behavior in focused component tests.
- [x] 2.2 Update the compact runtime and UX docs and add the required migration note; verify the docs match the shipped behavior and the migration check passes.

- [x] 2.3 Show simultaneous agent questions as selectable subject tabs in one HITL card; keep per-question drafts and first-pending default, reconstruct all unanswered tabs on reload, verify answer routing across resumes, and keep the card open on the next tab after Skip until no questions remain.
- [x] 2.4 Record the observed one-versus-two-call latency trade-off and the batch resume result in the PR.
- [x] 2.5 Stage every simultaneous question answer locally, allow edits and skips, then send one complete batch; verify no card flicker and failed-send recovery.
- [x] 2.6 Count nonblank free text as a draft during typing without requiring Next, and make closing the grouped card skip every pending question in one batch; verify both behaviors in focused frontend tests.
- [x] 2.7 Remove submitted tabs when the runtime accepts a batch, before the resumed stream ends, while preserving any later questions in the same exchange; verify the SSE ordering regression.
- [x] 2.8 Scroll overflowing subject tabs with wheel or trackpad input without dragging the scrollbar, and release vertical page scrolling at the strip ends; verify the focused card interaction.

## 3. Close-out

- [x] 3.1 Run targeted tests, full module suites, the root quality gate, and OpenSpec validation and sync; verify PR #2900 records the result and limitations. Evidence: runtime 1,745 passed, 11 skipped, 17 deselected; frontend 3,176 passed, 7 skipped; targeted batch tests 57 runtime and 109 frontend passed; root code-quality, migration check, and OpenSpec validation passed.
- [x] 3.2 Obtain independent correctness review and resolve its actionable findings.
- [ ] 3.3 Archive the change after merge.
