## 1. Turn contract

- [ ] 1.1 Define the command descriptor as a typed model beside `ChatMetadata`
      in `libs/fred-core/fred_core/history/history_schema.py` — command,
      appended text, prompt id, prompt name — and carry it as an optional
      field on `ChatMetadata`; verify a round-trip test stores a message with
      a descriptor and reads it back, and that a message without one still
      validates.
- [ ] 1.2 Give `make_user_text` an optional descriptor argument that lands on
      the turn's metadata; verify a test builds a turn with and without one
      and asserts the parts are identical in both cases — the descriptor
      changes metadata only.
- [ ] 1.3 Read the descriptor from `_AgentExecuteRequest.context` where
      `session_id` is already read in `agent_app.py`, and thread it to the
      user turn; no model change. Verify tests cover an ask carrying the key
      (descriptor on the stored turn), an ask without it (no descriptor), and
      an ask whose key holds junk (no descriptor, no error — the turn still
      stores and renders as text).
- [ ] 1.4 Confirm the descriptor never reaches the model: verify a test
      asserts the message handed to the agent is the assembled text alone.
- [ ] 1.5 Record the new `context` key and the turn-metadata key in
      `RUNTIME-EXECUTION-CONTRACT.md §8`; verify the entry states that both
      are optional, that no model changed, and that an older reader degrades
      to plain text.

## 2. Frontend — the command turn

- [ ] 2.1 Send the descriptor on the existing `runtime_context` the chat
      already builds in `useChatSse.ts`; verify a test asserts the key reaches
      the request. No client regeneration: `context` is untyped, so nothing in
      the generated client changes.
- [ ] 2.2 Build the command component for the user bubble using design-system
      tokens only — no fill, `1px solid --outline-muted`, `--radius-xs`, hover
      via `--state-on-secondary-container-hover`; verify a test asserts it
      renders the command and the appended text, and a review confirms no raw
      colour or arbitrary pixel value.
- [ ] 2.3 Make the component an activatable control with an accessible name
      naming the command; verify a test reaches and activates it by keyboard
      alone.
- [ ] 2.4 Select the component over the text part when the turn carries a
      descriptor; verify tests cover a turn with a descriptor (component, and
      the prompt text absent from the chat body), a turn without one (plain
      text), and a turn whose descriptor is unknown to the renderer (plain
      text, no error).
- [ ] 2.5 Open the side panel on the turn's own stored content when the
      component is activated; verify tests assert the panel shows the stored
      text, that it still does after the prompt has been rewritten, and that
      it still does once the prompt no longer exists.
- [ ] 2.6 Add the `fr` and `en` translations for the component's label and
      accessible name; verify no key resolves to its own name in either
      locale.

## 3. Close-out

- [ ] 3.1 Run `make code-quality` and `make test` in `apps/frontend`,
      `libs/fred-core` and `libs/fred-runtime`; verify all pass with no new
      warnings.
- [ ] 3.2 Run `/code-review` on the diff and address findings; verify no
      correctness finding remains open. The assistant cannot invoke it — ask
      the developer to run it, and record what it found.
- [ ] 3.3 Run the `fred-performance-reviewer` skill: this touches the turn
      build path, which runs per request; verify no new per-turn allocation or
      lookup was introduced on the send path.
- [ ] 3.4 Write the migration note under `docs/swift/ops/migrations/`,
      declaring the impact and stating that no data migration is needed and
      that older clients degrade to plain text; verify `make migration-check`
      passes from the repository root.
- [ ] 3.5 Record exact verification evidence in this change, then trim
      `PROMPT-COMMAND-TRIGGER-RFC.md` §2.5 to a pointer; verify the RFC no
      longer specifies the turn shape.
- [ ] 3.6 Archive the change once the implementation has merged; verify the
      `prompt-commands` capability spec carries the turn requirements.
