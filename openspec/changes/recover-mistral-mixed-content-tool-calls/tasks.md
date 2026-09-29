## 1. Captured regression

- [x] 1.1 Add a redacted mixed-fragment fixture matching the checkpoint boundaries in `test_tool_call_recovery.py`; verify the current middleware fails to recover its two calls before changing the parser.

## 2. Runtime recovery

- [x] 2.1 Accept plain string fragments around the exact sentinel in the bounded completed-message parser; verify the fixture produces two validated native calls and the existing rejection tests still pass.
- [x] 2.2 Recognize the same mixed fragment shape in stream decoding and suffix buffering; verify the fixture's marker and call syntax never appear in assistant or thought deltas when recovery succeeds.
- [x] 2.3 Exercise the recovered calls through ReAct and Deep, including tool-result pairing and the existing approval/budget path; verify targeted runtime tests pass.

## 3. Close-out

- [x] 3.1 Add targeted negative tests for a non-Mistral response, modified reference, invalid JSON/schema, ordinary text, and an existing native call; verify no accidental execution or duplicate call.
- [x] 3.2 Reconcile the execution contract and this change with the final behavior, record the checkpoint evidence and trace limitation in the existing design/task artifacts, and verify `openspec validate recover-mistral-mixed-content-tool-calls --strict` passes.
- [ ] 3.3 Run the root `make code-quality` once for the completed series, then push and open a draft PR linked to #2746; verify its checks and reviewable diff.
