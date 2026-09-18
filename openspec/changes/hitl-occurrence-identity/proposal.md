## Why

Human-in-the-loop resume identity rests on one narrowly true invariant, recorded in
`react_stream_adapter.py` and again on the SQL claim table: "`FredHitlMiddleware` has
exactly one `interrupt()` call site, so two DISTINCT FRED HITL occurrences always land
in different tasks and get different ids".

GitHub epic [#2642](https://github.com/ThalesGroup/fred/issues/2642) breaks that
invariant on purpose. It introduces an `ask_user` tool the model may call several times
in one turn, and a probe against the installed LangGraph shows that `ToolNode` runs all
of a turn's tool calls inside a single LangGraph task, so the successive pauses share
one `interrupt_id`:

```
3 ask_user calls in one turn -> pause 1: id=d57ce25a...  q1
                                pause 2: id=d57ce25a...  q2
                                pause 3: id=d57ce25a...  q3
                                distinct ids: 1 of 3
```

`interrupt_id` therefore stops being sufficient to say which pause an answer belongs to.
Two more places assume at most one platform-generated pause per exchange and break with
it: history pairs a request to a response by finding at most one of each per exchange,
and `HitlResponsePart` stores free text by hijacking `choice_id`.

This change makes occurrence identity explicit, ahead of the tool that needs it. It ships
no new tool and no UI rework - those are the two later changes under the same epic.

## What Changes

- `HumanInputRequest` carries an optional `occurrence_id`: the identifier of one pause
  among those sharing an `interrupt_id`. A pause raised from inside a tool sets it to
  that tool call's `tool_call_id`, which is stable across LangGraph's replay of a resumed
  task and unique per call.
- `RuntimeExecuteRequest` carries `occurrence_id` alongside `interrupt_id`, valid only
  together with `resume_payload`, mirroring the existing `interrupt_id` rule.
- Resume validation matches the `(interrupt_id, occurrence_id)` pair against the
  currently pending occurrences instead of `interrupt_id` alone. A pending occurrence
  that declares no `occurrence_id` keeps today's behaviour exactly.
- The durable single-use claim is keyed per occurrence rather than per interrupt, so two
  pauses sharing an `interrupt_id` cannot consume each other's claim.
- `HitlRequestPart` records the `occurrence_id`; `HitlResponsePart` records it too and
  gains a dedicated free-text field, so `choice_id` stops carrying typed text.
- History reconstruction pairs requests and responses by `occurrence_id` and stops
  assuming one HITL request and one HITL response per exchange.

No new tool, no composer control, no UI rework, no runtime event kind, and no Alembic
migration.

## Capabilities

### New Capabilities

- `human-in-the-loop`: establishes occurrence identity and the human response contract as
  the durable foundation the rest of epic #2642 builds on.

### Modified Capabilities

None.

## Impact

- Contracts: `fred-sdk` `contracts/runtime.py` (`HumanInputRequest`) and
  `contracts/execution.py` (`RuntimeExecuteRequest`); `fred-core`
  `history/history_schema.py` (`HitlRequestPart`, `HitlResponsePart`, `make_hitl_*`).
- Runtime: pending-occurrence extraction and resume validation in `agent_app.py`, the
  claim key in `sql_checkpointer.py`, the interrupt parser in `react_stream_adapter.py`,
  and history persistence of the resume payload.
- Frontend: `toThreadMessages.ts` pairing and pending detection; the resume payload built
  in `useChatSse.ts`. Generated clients are regenerated from the backend OpenAPI in the
  same change.
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` §8.39 (the HITL identity model this change
  amends).
- Backward compatibility: every new field is optional and absent on existing data, which
  keeps the current single-occurrence behaviour byte for byte.
