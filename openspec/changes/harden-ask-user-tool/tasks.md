## 0. Preconditions

- [x] 0.1 GitHub issue #3035 created (folds #3014) and linked in proposal.md.
- [ ] 0.2 Before archiving, re-apply this delta onto the current requirement text if `refine-agent-question-answers`, `add-agent-initiated-human-questions` or `refresh-hitl-card-visuals` was archived first. Verify: `openspec validate harden-ask-user-tool --strict` and a diff of the archived requirement keeps both changes' edits.

## 1. Runtime

- [x] 1.1 Add `ASK_USER_DESCRIPTION` to `runtime_support/ask_user.py`: use the tool for any decision, preference or missing detail instead of asking in the reply; short subject title; at most four choices; never add an "Other" choice; ask without choices for an open answer. Use it in `react/react_tool_resolution.py` and `graph/graph_runtime.py`, deleting both inline strings. Update the `choices` field description. Verify: test that both runtimes expose the same description.
- [x] 1.2 Add a `mode="before"` validator on `AskUserArgs` that drops generic "Other" choices (normalised label in the fixed set from design.md) and sets `allow_free_text` to true when it drops one. Verify: parametrised tests for "Autre", "Other", "Autre (précise si tu veux)", "Something else" dropped; "Other country" kept; four choices plus "Autre" accepted; "Oui" plus "Autre" becomes one choice with free text.
- [x] 1.3 Delete the "requires choices or free text" check and compute `free_text = allow_free_text or len(choices) != 1`. Verify: `ask_user({"question": "...", "tool_call_id": "x"})` interrupts with `free_text: true` (#3014 acceptance); the no-choices payload is removed from `test_ask_user_rejects_invalid_question_forms`; the single-choice behaviour is unchanged.

## 2. Close-out

- [x] 2.1 Quality gates in `libs/fred-runtime`: `make code-quality`, `make test`. Run the `fred-performance-reviewer` skill on the tool call site (validation only, no I/O added). Verify: green, counts recorded here. Done: code-quality clean (0 errors); `make test` 1911 passed, 11 skipped. The `test_tool_call_recovery` case that rejected a question-only call was removed, since that call is now valid. Performance: reviewed by hand rather than through the skill. The change adds only argument normalisation over at most a handful of choice labels: no I/O, no shared state, no new KPI.
- [x] 2.2 Migration note `docs/swift/ops/migrations/3035-harden-ask-user-tool.md` (impact `none`). Verify: `make migration-check`.
- [x] 2.3 Manual check: in managed chat with agent questions on, ask "pose-moi une question à choix" and an open question. Verify: the agent uses the tool (best effort), shows no duplicate "Other", and the open question pauses for free text.
  - Done 2026-10-10 on mistral-small-latest, in a new conversation (local session a05371ce):
    - "Pose moi une question" called `ask_user` with no choices and no `allow_free_text`; the question paused as free text (#3014).
    - "pose moi une question à plusieurs choix" called `ask_user` with four choices and no "Other"; the card showed a single editable "Other" row.
    - Residual: after a garbled answer, the agent asked a follow-up in plain text.
  - The first wording ("whenever you need a decision…") was not enough. In a conversation where the agent had already asked in text, it judged that "ask me a question" did not require the tool. The description now says the tool is the only way to ask the user anything, including when the user asks to be asked a question.
- [ ] 2.4 Archive after merge, then close #3035 and #3014. Verify: `openspec validate harden-ask-user-tool --strict`.
