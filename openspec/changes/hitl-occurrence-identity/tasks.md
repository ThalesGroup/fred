Change 1 of 3 under GitHub epic #2642. This slice ships occurrence identity and the human
response contract only; the `ask_user` tool (change 2) and the HITL UI rework (change 3)
depend on it and are tracked separately.

## 1. Contract

- [x] 1.1 Add an optional `occurrence_id` to `HumanInputRequest`, documenting the single
      rule that separates it from `interrupt_id` and `checkpoint_id`: it names one pause
      within an interrupt, and derives from the raising tool call.
- [x] 1.2 Add `occurrence_id` to `RuntimeExecuteRequest`, rejected unless `resume_payload`
      is set, mirroring the existing `interrupt_id` validator.
- [x] 1.3 Add `occurrence_id` to `HitlRequestPart`; add `occurrence_id` and a dedicated
      free-text field to `HitlResponsePart`, and make `choice_id` optional.
- [x] 1.4 Extend `make_hitl_request` / `make_hitl_response` for the new fields.

## 2. Runtime

- [x] 2.1 Replace the pending-id extraction with pending-occurrence extraction returning
      `(interrupt_id, occurrence_id | None)` pairs, still reading `pending_writes`
      directly so it keeps running ahead of authorization.
- [x] 2.2 Validate the resume against the pair: require a matching `occurrence_id` when
      the pending occurrence declares one, and keep interrupt-only validation when it
      does not.
- [x] 2.3 Key the single-use claim per occurrence via a composite claim key, leaving the
      claim table's columns untouched, and verify a bare id can never collide with a
      composite one.
- [x] 2.4 Preserve `occurrence_id` through interrupt parsing in the stream adapter.
- [x] 2.5 Persist `occurrence_id` and the answer text from the resume payload into
      history instead of deriving a `choice_id` string from it.
- [x] 2.6 Return the pending occurrences from the admission gate and skip persisting a
      pause a previous run already surfaced, so a sibling re-raised by a resume keeps
      one history row.
- [x] 2.7 Send a typed CLI answer in the same `answer` field the web client uses, so
      terminal free text is stored as text instead of as the chosen `choice_id`.

## 3. Frontend

- [x] 3.1 Echo `occurrence_id` verbatim on resume, alongside `interrupt_id`.
- [x] 3.2 Pair HITL requests with responses by `occurrence_id` in history
      reconstruction, replacing the at-most-one-per-exchange lookups, with position-based
      pairing retained for rows carrying no `occurrence_id`.
- [x] 3.3 Derive pending state from the first unanswered request in the exchange rather
      than from the presence of any response.
- [x] 3.4 Regenerate the API clients from the backend OpenAPI and commit them with the
      backend change.

## 4. Verification

- [x] 4.1 Cover sibling pauses sharing an `interrupt_id`: independently answerable,
      each answer applied to its own occurrence, a stale answer refused.
- [x] 4.2 Cover replay stability: a resumed task replayed from the top yields the same
      `occurrence_id`.
- [x] 4.3 Cover claim isolation between siblings, and concurrent attempts on one
      occurrence.
- [x] 4.4 Cover backward compatibility: a pause with no `occurrence_id`, and history rows
      persisted before this change, behave exactly as today.
- [x] 4.5 Assert that a pause raised from within a tool call always declares an
      `occurrence_id`.
- [x] 4.6 Update `RUNTIME-EXECUTION-CONTRACT.md` §8.39 with the amended identity model.
- [x] 4.7 Run `make code-quality` and `make test`, the performance review for the touched
      resume path, and an independent `/code-review` pass before push.

## Handoff

Archive this change once merged. Change 2 (`ask_user` tool, composer control, skip path,
Deep inheritance proof, `choice_step` alignment) depends on the contract landed here.
Pause lifetime and expiry remain with epic #1080 and must not be absorbed into this
checklist.
