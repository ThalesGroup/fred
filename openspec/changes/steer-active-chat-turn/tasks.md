## 1. Runtime steering

- [x] 1.1 Add a process-local active-run mailbox and an authenticated steering endpoint; verify a focused runtime test covers owner/agent mismatch, duplicate ids, and no active run.
- [x] 1.2 Add a root ReAct/Deep before-model hook and a typed delivery event; verify a focused runtime test places the user message after a completed tool batch and only once.
- [x] 1.3 Persist the delivery event as an ordered user history row; verify a focused history test.

## 2. Managed chat

- [x] 2.1 Keep plain-text composer submission available during streaming, queue it per session, and drain one ordinary turn at a time; verify focused hook tests cover order and pause behavior.
- [x] 2.2 Render pending rows above the composer with edit, remove, and short immediate-delivery actions; verify focused component tests and localized labels.
- [x] 2.3 Send the steering request and reconcile only on the delivery event, preserving a pending row on refusal or missed boundary; verify focused SSE and page tests.

## 3. Review

- [x] 3.1 Validate the OpenSpec change, run focused checks, review the full diff against `swift`, and record prototype limits in the draft PR or task response.
