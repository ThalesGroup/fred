## 1. Retained baseline and revised acceptance

This checklist tracks the approved reduced scope. Automated checks and independent
review are recorded in verification.md. Remaining interactive acceptance is pending;
the developer will run final root checks after returning.

- [x] 1.1 Reframe the existing proposal, design and delta spec around preserved Graph work, explicit choice and single-active-execution usage; verify that distributed recovery and ReAct/Deep implementation are excluded.
- [x] 1.2 Retain sync durability, opaque interruption identity, current authorization, existing provider admission and completed-task reuse; verify the retained paths against the revised spec and existing regression coverage.

## 2. Remove terminal cleanup and finish local lifecycle

- [x] 2.1 Remove `_end_unfinished_run`, `_RUN_KEY`, run ownership stamping and cleanup-only helpers/imports after checking consumers. Replace cleanup tests with preservation scenarios for node errors, step limits and publication timeout. Verify native engine state remains continuable without new recovery machinery; report a contract gap if not.
- [x] 2.2 Close and await the underlying compiled stream inside the existing admission scope. Verify a close during a custom progress event waits for node teardown before another continuation can acquire admission.
- [x] 2.3 Retain existing provider locks, capacity bounds and unsupported-provider rejection without adding leases, heartbeats or ordinary-turn coordination; verify no permanent technical HITL claim is reintroduced.

## 3. Align request and user decisions

- [x] 3.1 Reject non-empty Continue input at the public request boundary and regenerate the runtime client. Verify both execution routes cannot record an ignored user instruction.
- [x] 3.2 Localize unfinished/uncertain-state wording, explain Restart is not rollback and add Later using local dismissal only. Verify no request on Later and rediscovery on the next message; retain original command resend and ordinary HITL behavior.
- [x] 3.3 Base send acceptance and Stop consumption on the existing HTTP acceptance signal. Verify preparation/HTTP refusal restores controls while a post-acceptance stream failure triggers no automatic retry.

## 4. Prove the consumer outcome

- [x] 4.1 Extend the existing domain-neutral prepare/publish/finalize fixture with stable content, business identity, receipt and an idempotent test destination. Verify blocked/failed preparation persistence produces zero publications.
- [x] 4.2 Verify real process restart preserves preparation, and commit followed by lost response recovers the same publication with one business effect. Include a live-process timeout so recovery is not limited to process death.
- [x] 4.3 Verify failed receipt persistence does not claim durable completion, and a durable receipt followed by interrupted finalization requires zero additional publication calls.
- [x] 4.4 Verify current authorization refusal, stale identity, ordinary HITL and unchanged ReAct/Deep behavior through existing public paths. See verification.md for executed checks and exclusions.

## 5. Reconcile and review

- [x] 5.1 Update existing runtime contract, UX and migration note to the final implementation. Verify they state single-active-execution usage, retained provider prerequisites and changed behavior after failure, with no process-death or exactly-once claim.
- [x] 5.2 Reconcile the existing PR description and verification evidence; preserve historical evidence as such. Record the real fred-rags adapter validation as downstream adoption evidence, not something the generic fixture proves.
- [x] 5.3 Review the full final diff against swift, including an independent bounded review. Evaluate findings against this scope before adding mechanisms; prefer deletion or explicit constraints. Run only authorized verification and record exclusions.
- [ ] 5.4 When revised acceptance is met, sync/archive this change and leave #2892 open for broader guarantees. Record ReAct/Deep lessons without implementing those follow-ups here.
