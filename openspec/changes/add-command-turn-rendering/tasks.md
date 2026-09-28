## 1. Turn contract

- [x] 1.1 Define the command descriptor as a typed model beside `ChatMetadata`
      in `libs/fred-core/fred_core/history/history_schema.py` — command,
      appended text, prompt id, prompt name — and carry it as an optional
      field on `ChatMetadata`; verify a round-trip test stores a message with
      a descriptor and reads it back, and that a message without one still
      validates.
- [x] 1.2 Give `make_user_text` an optional descriptor argument that lands on
      the turn's metadata; verify a test builds a turn with and without one
      and asserts the parts are identical in both cases — the descriptor
      changes metadata only.
- [x] 1.3 Add the optional descriptor field to `RuntimeContext` in
      `libs/fred-sdk`, beside the other per-turn frontend values; verify a
      test round-trips a context carrying one through `model_dump()`.
- [x] 1.3b Read it from the internal context dict where `session_id` is read
      in `agent_app.py` and thread it to the user turn; verify tests cover a
      request carrying it (descriptor on the stored turn), one without it (no
      descriptor), and one whose value is malformed (no descriptor, no error
      — the turn still stores and renders as text).
- [x] 1.4 Confirm the descriptor never reaches the model: verify a test
      asserts the message handed to the agent is the assembled text alone.
- [x] 1.5 Record the new `RuntimeContext` field and the turn-metadata key in
      `RUNTIME-EXECUTION-CONTRACT.md §8`; verify the entry states that both
      are optional and that an older reader degrades to plain text.

## 2. Frontend — the command turn

- [x] 2.1 Run `make update-runtime-api` in `apps/frontend` and commit the
      regenerated client, then send the descriptor on the `runtime_context`
      the chat already builds in `useChatSse.ts`; verify the generated
      `RuntimeContext` type carries the field and a test asserts it reaches
      the request.
- [x] 2.2 Build the command component for the user bubble using design-system
      tokens only — no fill, `1px solid --outline-muted`, `--radius-xs`, hover
      via `--state-on-secondary-container-hover`; verify a test asserts it
      renders the command and the appended text, and a review confirms no raw
      colour or arbitrary pixel value.
- [x] 2.3 Make the component an activatable control with an accessible name
      naming the command; verify a test reaches and activates it by keyboard
      alone.
- [x] 2.4 Select the component over the text part when the turn carries a
      descriptor; verify tests cover a turn with a descriptor (component, and
      the prompt text absent from the chat body), a turn without one (plain
      text), and a turn whose descriptor is unknown to the renderer (plain
      text, no error).
- [x] 2.5 Open the side panel on the turn's own stored content when the
      component is activated; verify tests assert the panel shows the stored
      text, that it still does after the prompt has been rewritten, and that
      it still does once the prompt no longer exists.
- [x] 2.6 Add the `fr` and `en` translations for the component's label and
      accessible name; verify no key resolves to its own name in either
      locale.

## 3. Close-out

- [x] 3.1 Run `make code-quality` and `make test` in `apps/frontend`,
      `libs/fred-core` and `libs/fred-runtime`; verify all pass with no new
      warnings.
- [x] 3.2 Run `/code-review` on the diff and address findings; verify no
      correctness finding remains open. The assistant cannot invoke it — ask
      the developer to run it, and record what it found.
- [x] 3.3 Run the `fred-performance-reviewer` skill: this touches the turn
      build path, which runs per request; verify no new per-turn allocation or
      lookup was introduced on the send path.
- [x] 3.4 Write the migration note under `docs/swift/ops/migrations/`,
      declaring the impact and stating that no data migration is needed and
      that older clients degrade to plain text; verify `make migration-check`
      passes from the repository root.
- [x] 3.5 Record exact verification evidence in this change, then trim
      `PROMPT-COMMAND-TRIGGER-RFC.md` §2.5 to a pointer; verify the RFC no
      longer specifies the turn shape.
- [ ] 3.6 Archive the change once the implementation has merged; verify the
      `prompt-commands` capability spec carries the turn requirements.

Not here, by decision (2026-09-28): the `fr`/`en` Help Center pages ship with
the last slice of this feature, the one that makes a command runnable from the
chat. Until then the field does nothing, so documenting it would teach a
behaviour nobody can use. Carried in `PROMPT-COMMAND-TRIGGER-RFC.md` §2.7.

## Verification evidence

Recorded 2026-09-28.

**Backend.** `make code-quality` clean in `libs/fred-core`, `libs/fred-runtime`
and `libs/fred-sdk`. `make test`: fred-core **977 passed**, fred-runtime
**1627 passed** (11 skipped on missing optional deps, pre-existing), fred-sdk
**487 passed**.

**Frontend.** `make code-quality` clean (tsc, prettier, eslint). `make test` →
**2923 passed, 7 skipped, 251 files**.

`make migration-check` valid.

**Correction to the plan, made while building.** The change was proposed on the
belief that the descriptor could ride as an untyped key in
`_AgentExecuteRequest.context`. That is the internal/dev path; the frontend
uses `RuntimeExecuteRequest` with a **typed** `RuntimeContext`. So it is a
typed field after all — but on `RuntimeContext`, which is explicitly the model
the frontend fills per turn (`context_prompt_text`, `language`,
`attachments_markdown` and a dozen more), and which is `model_dump()`ed into
the internal context dict, so the runtime read still costs one key. The
artifacts were corrected before implementation.

**`/code-review`** (task 3.2) was run by the developer. Five findings, all
addressed: a memo broken by an inline callback, an `aria-label` that swallowed
the appended text, a 1000-row listing that could hide a held command from the
import suffixer, `promote_prompt` silently dropping the command, and helper
text promising a trigger this release does not have.

A second `/code-review` pass, run by the developer over the whole branch once
the trigger slice landed, reached this slice's code again and found nothing new
in it — its four findings were all in the field and trigger slices. Recorded in
`add-prompt-command-trigger/tasks.md`.

**`fred-performance-reviewer`** (task 3.3) found one further issue, of the same
class as the first: `ConversationThread` handed each row a callback built per
message, defeating `UserTurn`'s own memo for command turns on every streamed
frame. Fixed by passing the turn's values to a stable callback instead of a
closure, and locked by
`ConversationThread.rowCallbacks.test.tsx`, which fails against the previous
shape.

It also measured what the change costs where it touches storage:
`list_commands_by_team` plans as an **Index Only Scan with `Heap Fetches: 0`**
against the partial unique index, and it replaced a `list_by_team(limit=1000)`
that fetched whole rows including the `text` column — so the import path does
less work than before. `_turn_command` runs after the SSE stream is fully
sent, costing a dict read plus, at most, a four-field validation. No new
metric, label, external call, client or module-level state; hot-path invariants
otherwise not applicable to this diff.
