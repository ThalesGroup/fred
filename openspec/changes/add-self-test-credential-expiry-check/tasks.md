Agent paths are under `apps/fred-agents/`; frontend paths under
`apps/frontend/src/`.

## 1. Harness agent

- [x] 1.1 Add the `settings.hold_seconds` (integer, default 0, clamped to the declared maximum) and `settings.check_access` (boolean, default off) tuning fields in `fred_agents/self_test/graph_agent.py`, and a `hold` node ahead of `retrieve`.
- [x] 1.2 In `fred_agents/self_test/graph_steps.py`, have `hold_step` sleep in slices, emitting a heartbeat per slice on the live channel and one status at the hold's end; a zero hold changes nothing.
- [x] 1.3 Put the call made before the wait in its own node, so its status is flushed before the hold rather than after it.
- [x] 1.4 In access-check mode, call the metadata service as the person before the hold (status `credential_baseline`) and again after it (status `protected_call_succeeded`), read no documents, and emit `credential_renewed` when the credential in hand changed across the second call.
- [x] 1.5 Classify a failed call as the person through one helper shared by both call sites: one message for an expired credential, one for any other refusal, one for a transport failure — none carrying upstream response text.
- [x] 1.6 Verify in `tests/test_self_test_agent.py`, with the sleep injected so no test waits: a zero hold goes straight through; a set hold emits heartbeats then its status; the fields are registered and bounded; access-check mode makes both calls, reads no document and reports renewal only when observed; each classifier branch returns its own message and echoes no upstream text.

Dependencies: none. Owns the two agent modules and their test.

## 2. Check in the pipeline

- [x] 2.1 Let `rework/features/pipeline/actions.ts` stream a turn on a supplied credential, declared in `rework/features/pipeline/types.ts`, and classify the agent's fixed expiry message whether it arrives as an execution error or as the turn's final text.
- [x] 2.2 Add `rework/features/pipeline/scenarios/credentialExpiryScenario.ts`: capture the session's current access token once, size the hold from its remaining lifetime plus the margin, skip above the bound and with no realm, enroll the run's instance with the hold and access-check mode, run the one turn on the captured credential, apply the verdict rules, and delete the instance in a `finally` tolerating one already gone.
- [x] 2.3 Stop enrollment in `rework/features/pipeline/usePipelineRun.ts` from removing other instances of the same template, so concurrent runs keep theirs.
- [x] 2.4 Report the pre-expiry evidence as its own step the moment it arrives, through a status callback on the streaming turn, and name the template the temporary agent comes from.
- [x] 2.5 Verify in `scenarios/credentialExpiryScenario.test.ts` with fake deps: no library, document, prompt or session is touched; the captured credential is used for the turn and appears in no report; skip above the bound and without a realm; each missing piece of evidence fails; a hold ending before expiry is inconclusive; a refusal reports the fixed explanation from either arrival path; admission refusal is not expiry; a cancelled creation reads as cancelled; the instance is deleted on every path.

Dependencies: 2.2 needs 2.1 and the field names from 1.1. Owns the pipeline modules named above.

## 3. Page

- [x] 3.1 Give the check its own sub-section of the authorization self-test in `rework/components/pages/admin/SelfTestPage/SelfTestPage.tsx`, with one action, its own report panel, no password field, and disabled while any run on the page is in flight; add the `en` and `fr` strings describing the wait and what the run creates.
- [x] 3.2 Gate the action behind a notice the admin accepts: quote the wait from the session's remaining lifetime through the same helper the run sizes its hold with, say the page must stay open and what an early close leaves behind, and start nothing until it is accepted.
- [x] 3.3 Verify in a test beside the page component: the action needs no password and carries no other profile's credentials, it is unavailable while another run is in flight, it reports into its own panel, nothing of the check is offered without a realm, and nothing starts until the notice — quoting the wait, or shown without a figure when the lifetime is unknown — is accepted.

Dependencies: needs 2.2. Owns the page component, its test and the locale files.

## 4. Documentation

- [x] 4.1 Describe the check in the `/admin/self-test` entry of `docs/swift/TESTING.md`: own session's token, duration and skip bound, the single temporary instance, red until in-turn renewal exists.

Dependencies: none.

## 5. Live verification

- [x] 5.1 Run the check in a browser against a running deployment as a platform admin: confirm the wait matches the session's remaining lifetime, that it ends red at the post-hold call with the fixed expiry explanation, and that the temporary agent instance is gone afterwards.

Dependencies: needs 1-4.

Verification: `make code-quality` and `make test` in `apps/fred-agents` and
`apps/frontend`, plus the live run above.
