## 1. Tracking and contract foundation

- [x] 1.1 Create a dedicated GitHub issue for this second slice, link epic #2642 and this change; [#2836](https://github.com/ThalesGroup/fred/issues/2836) is open in `swift ga`. Record its URL in the implementation PR.
- [x] 1.2 Prove with the installed LangGraph that a model-hidden injected tool call id reaches the shared tool binder and stays stable across pause/replay; local probe: model schema exposed only `question`, both executions saw `call-123`, and the final `ToolMessage` kept `call-123`.
- [x] 1.3 Add optional `RuntimeContext.ask_user`, a typed choice/text/skipped answer parser, and the compatible Graph choice helper; 11 targeted SDK and Graph tests passed, including legacy string answers.
- [x] 1.4 Add an optional skipped response state to `HitlResponsePart` and its constructor; 6 focused history tests passed for old JSON and new skipped rows.

## 2. Runtime question tool and admission

- [x] 2.1 Mount the pure `ask_user` tool only for enabled interactive turns through the shared ReAct/Deep resolver and binder; verify tool catalog, collision, absence, and injected occurrence-id tests.
- [x] 2.2 Validate each pending agent-question answer before the single-use claim, then return choice/text or skipped JSON with a localized continuation instruction to the matching tool call; verify invalid answers leave the pause retryable and approval-gate behavior is unchanged.
- [x] 2.3 Persist skipped answers as HITL response rows and preserve choice-plus-comment fields; verify history reload finds no pending question after a skip.
- [x] 2.4 Exercise real compiled ReAct and Deep turns for choice, text, choice plus comment, skip, and sibling questions sharing an interrupt id; verify each result reaches the correct `ToolMessage` and the turn continues.

- [x] 2.5 Bound `ask_user` to four agent-selected choices in its schema and tool guidance; reject longer calls before pausing without truncation. Verify the schema and validation at final PR verification.

## 3. Managed chat

- [x] 3.1 Emit the platform-owned `ask_user_toggle` in control-plane execution preparation with its default on; verify the control-plane preparation test and absent-control compatibility.
- [x] 3.2 Store the toggle per conversation and send `RuntimeContext.ask_user` on new turns only when the fresh preparation offers it, including the first turn before eager controls load; verify true, false, absent, first-turn, and session-switching tests.
- [x] 3.3 Extend the existing HITL prompt to submit a choice with optional comment, show skip and a matching close action only for agent questions, and lay out choices vertically; verify component and resume-payload tests, including input length and keyboard behavior.
- [x] 3.4 Keep a pending question answerable when the toggle changes during its pause, and render a skipped response after reload; verify managed-chat resume and history-reconstruction tests.
- [x] 3.5 Regenerate runtime and control-plane OpenAPI clients from backend sources; verify generated-file diffs and frontend typecheck.

- [x] 3.6 Render optional choice descriptions beneath labels in the same HITL button, preserving the single-line treatment when absent; verify with a managed chat example and focused component coverage.

- [x] 3.7 Show accepted answers immediately below their `ask_user` tool line, and show the offered choices with the selected one highlighted in the tool drawer; verify choice labels, text, comments, skip, and reload after manual UI validation.
- [x] 3.8 Keep a pending `ask_user` tool call in progress rather than error and place a compact raised Send button immediately left of Skip for free-text questions; inspect confirmation, choice, text, choice-with-comment, and tool-approval cards.
- [x] 3.9 Disable new managed-chat messages and commands during an `ask_user` pause and its resume preflight, without blocking other conversations; restore the composer after answer or skip.

## 4. Documentation and release verification

- [x] 4.1 Amend the runtime and control-plane product contracts, update `COMPONENT-UX.md`, and add the required English operator migration note; verify each document describes the shipped behavior and rollback order.
- [x] 4.2 Focused tests and root `make code-quality` passed. Root `make test` was interrupted externally during control-plane tests; every module completed successfully through that run or a separate full module run (control plane: 1,428 passed; knowledge flow: 1,461 passed; frontend: 2,984 passed).
- [ ] 4.3 Performance review found only one additional async checkpoint read on authenticated HITL resumes, with no blocking work or new shared state. Independent correctness review remains for the draft PR.
- [x] 4.4 Delta spec is synced to the main spec and `openspec validate --strict` passes.
- [x] 4.5 Route the no-LLM Graph test assistant confirmation, choice, text, and choice-with-comment examples through the platform `ask_user` tool; verify tool trace, pause and resume, skip, control gating, and the managed chat answer card.
- [ ] 4.6 Confirm the draft PR and archive after merge.
