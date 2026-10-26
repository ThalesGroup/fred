## 1. Runtime steering

- [x] 1.1 Add a process-local active-run mailbox and an authenticated steering endpoint; verify a focused runtime test covers owner/agent mismatch, duplicate ids, and no active run.
- [x] 1.2 Add a root ReAct/Deep before-model hook and a typed delivery event; verify a focused runtime test places the user message after a completed tool batch and only once.
- [x] 1.3 Persist the delivery event as an ordered user history row; verify a focused history test.
- [x] 1.4 Preserve undelivered steering across a human-input pause and matching resume; verify a focused mailbox and middleware test.

## 2. Managed chat

- [x] 2.1 Keep plain-text composer submission available during streaming, queue it per session, and drain one ordinary turn at a time; verify focused hook tests cover order and pause behavior.
- [x] 2.2 Render a compact, collapsible pending panel like `write_todos`; keep each message on one ellipsized line, use the composer menu pattern with edit/delete icons, and use Fred's shared secondary tonal button labeled `Send`/`Envoyer` for immediate delivery. Verify focused component tests and localized labels.
- [x] 2.3 Send the steering request and reconcile only on the delivery event, preserving a pending row on refusal or missed boundary; verify focused SSE and page tests.

## 3. Review

- [x] 3.1 Validate the OpenSpec change, run focused checks, review the full diff against `swift`, and record prototype limits in the draft PR or task response.

## 4. Shared multi-replica delivery

- [x] 4.1 Replace the process-local mailbox with one SQL-backed active-turn row, using the existing runtime async engine and one migration; cover cross-replica offer, ordered idempotent take, lease, stale turn, and close races in focused tests.
- [x] 4.2 Carry a turn identity through the stream and steering requests; preserve accepted undelivered messages through HITL resume on another replica, and reject stale offers.
- [x] 4.3 Update the generated runtime API contract, deployment note and PR description; verify the two-replica path, targeted tests, migration check, and branch review.
