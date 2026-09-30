## 1. Captured regression

- [x] 1.1 Add a redacted mixed-fragment fixture matching the checkpoint boundaries in `test_tool_call_recovery.py`; verify the current middleware fails to recover its two calls before changing the parser.

## 2. Runtime recovery

- [x] 2.1 Accept plain string fragments around the exact sentinel in the bounded completed-message parser; verify the fixture produces two validated native calls and the existing rejection tests still pass.
- [x] 2.2 Recognize the same mixed fragment shape in stream decoding and suffix buffering; verify the fixture's marker and call syntax never appear in assistant or thought deltas when recovery succeeds.
- [x] 2.3 Exercise the recovered calls through ReAct and Deep, including tool-result pairing and the existing approval/budget path; verify targeted runtime tests pass.

## 3. Close-out

- [x] 3.1 Add targeted negative tests for a non-Mistral response, modified reference, invalid JSON/schema, ordinary text, and an existing native call; verify no accidental execution or duplicate call.
- [x] 3.2 Reconcile the execution contract and this change with the final behavior, record the checkpoint evidence and trace limitation in the existing design/task artifacts, and verify `openspec validate recover-mistral-mixed-content-tool-calls --strict` passes.
- [x] 3.3 Run the root `make code-quality` once for the completed series, then push and open a draft PR linked to #2746; verify its checks and reviewable diff.

## 4. Follow-up captured regressions

- [x] 4.1 Add redacted tests for repeated exact markers in one response and a native call carrying marked content; verify the current parser rejects the former and the current stream publishes the latter as Planning.
- [x] 4.2 Accept only validated repeated markers in the bounded completed-message parser; verify all calls execute once, and adjacent, modified, unknown, or invalid later markers reconstruct no calls.
- [x] 4.3 Withhold pending marked syntax when a completed response already has native calls, preserving safe prose and native IDs; verify neither assistant nor Planning events contain the encoded call.
- [x] 4.4 Reconcile the execution contract and OpenSpec artifacts, run focused ReAct and Deep suites, strict OpenSpec validation, and the root quality gate; push the draft PR update and verify its checks.
