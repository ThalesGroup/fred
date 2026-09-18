## 1. Todo snapshot projection

- [x] 1.1 Add a typed, strict `write_todos` snapshot parser and newest-first conversation selector, and verify focused unit tests cover every supported status, malformed payloads, failed updates, the last-valid fallback, and explicit empty snapshots.
- [x] 1.2 Reuse the parser in trace grouping to omit represented todo call/result pairs while retaining malformed calls, failed calls, orphan results, and unrelated tools, and verify the focused trace utility tests pass.

## 2. Task panel component

- [x] 2.1 Implement the token-based, accessible `AgentTodoPanel` molecule with remaining-count, status indicators, completed-task treatment, and constrained expanded content, and verify component tests cover mixed states and all-complete state.
- [x] 2.2 Add per-session disclosure persistence with the existing local-storage hook and automatic defaults for active versus completed plans, and verify component or hook tests cover reload, session isolation, and explicit-preference precedence.

## 3. Managed chat integration

- [x] 3.1 Derive the current snapshot from `useManagedChat().messages` and mount the panel between the conversation stage and composer without affecting the initial empty state, and verify page tests cover the placement plus live and restored message inputs.
- [x] 3.2 Add English and French localized panel copy and update `docs/swift/ux/COMPONENT-UX.md` with the shipped placement, behavior, persistence, and trace relationship; verify translation keys resolve in component tests and the documentation matches the implementation.

## 4. Verification and close-out

- [x] 4.1 Run the focused frontend tests for the selector, trace grouping, panel, and managed-chat integration and record the passing commands and counts in the change verification evidence.
- [x] 4.2 Run `make code-quality` and `make test` in `apps/frontend`, fix failures attributable to this change, and record exact results and any unrelated limitation.
- [x] 4.3 Run the required independent code review on the complete mergeable diff, address actionable findings, and rerun every affected check.
- [x] 4.4 Reconcile the OpenSpec artifacts with the implemented behavior, record final verification evidence, validate the change strictly, and archive it so `deep-agent-todo-panel` becomes the current capability spec.
