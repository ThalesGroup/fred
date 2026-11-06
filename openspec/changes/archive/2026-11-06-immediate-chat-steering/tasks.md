## 1. Durable history and migration

- [x] 1.1 Add message identity and delivery state to shared history storage, with atomic provisional rank allocation and idempotent lookup; verify concurrent and retry cases in focused store tests.
- [x] 1.2 Add one runtime migration that drops unconsumed mailbox messages with its table while preserving existing history; verify upgrade and downgrade paths in migration tests.

## 2. Runtime delivery and checkpoints

- [x] 2.1 Replace mailbox operations with history-backed submission and safe-boundary consumption for ReAct and Deep; verify tool-batch, repeated-boundary, cross-replica, and HITL scenarios.
- [x] 2.2 Reconcile delivered message identity with checkpoint state after interruption, and implement ordinary-turn continuation for a message that missed the boundary; verify crash/retry and no-duplicate model context scenarios.
- [x] 2.3 Assign definitive ranks at delivery and persist the trace before stream close without duplicate user rows; verify sorted reloaded history, tool pairing, and consecutive turns.

## 3. Managed chat interface

- [x] 3.1 Submit active-turn text directly as an optimistic chat row, reconcile the persisted row by message identity, and show pending/brief delivered indicators; verify focused hook and rendering tests.
- [x] 3.2 Remove the browser queue, panel, controls, and translations, and resume persisted pending messages when eligible; verify navigation, reload, Stop, HITL, and Graph behavior.

## 4. Integration and delivery

- [x] 4.1 Update runtime and UX contracts plus migration operations guidance; verify documentation matches the final API and deployment sequence.
- [x] 4.2 Run focused backend/frontend tests, root quality once, and an independent branch review against the target branch; record findings and dispositions.
- [x] 4.3 Reconcile OpenSpec artifacts, sync and archive the change, create or link the tracking issue, and push a draft PR; verify its diff and migration count.
