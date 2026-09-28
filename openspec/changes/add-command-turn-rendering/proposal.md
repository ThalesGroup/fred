## Why

`add-prompt-command-field` gave a prompt a command. `PROMPT-COMMAND-TRIGGER-RFC.md`
§2.4 then says what running one means: **the prompt's text is sent to the
agent, and the user never sees it pass through the composer**. §2.5 says the
chat body must not show it either — the turn reads as *the command*, and the
prompt is one click away in a panel.

That rendering has to exist **before** the `/` trigger, not after. A trigger
merged on its own would send the whole prompt text and the transcript would
print it in the chat body — exactly the outcome the RFC rules out. Building
the turn rendering first keeps every merged state correct: this change is
invisible until something writes a descriptor, and the trigger slice that
follows turns it on.

## What Changes

- A user turn MAY carry a **command descriptor**: the command, the text the
  user appended after it, and the id and name of the prompt it ran.
- The turn's content is unchanged in kind: it holds the **full assembled
  text** — the prompt plus anything appended. This is not a choice. History is
  replayed to the model on every later turn, so a turn holding only
  `/summary 33 lignes` would leave the model reading a command it knows
  nothing about, and the conversation would stop making sense from the second
  turn on.
- The transcript renders a turn that has a descriptor as a **command
  component** instead of its text. Clicking it opens, in the existing side
  panel, the text that was actually sent.
- A reader that does not know the descriptor renders the turn as plain text.
  Degraded, not broken.

Nothing writes a descriptor yet. The composer trigger is the next slice.

## Capabilities

### Modified Capabilities

- `prompt-commands`: gains how a turn that ran a command is stored and
  rendered. The capability spec is still in flight as
  `openspec/changes/add-prompt-command-field/specs/prompt-commands/spec.md`
  (issue #2828, implemented, awaiting merge and archive); this change adds
  requirements to it rather than opening a second capability for the same
  feature.

## Impact

**Runtime — `libs/fred-runtime`, `libs/fred-core`**

No model changes. `_AgentExecuteRequest.context` is already an open
`dict[str, Any]` and is already the channel for caller-supplied facts about a
turn that are not the message — it carries `session_id`, `user_id` and
`team_id` today, and the frontend already sends it as `runtime_context`. The
descriptor becomes one more key in it.

What that costs: one key read where `session_id` is read, one optional
argument threaded to `make_user_text`, and a line in
`RUNTIME-EXECUTION-CONTRACT.md` recording the new `context` key. No field is
added to a frozen model.

`ChatMetadata` is `extra="allow"`, so the storage side needs no schema change
either and an older reader ignores the key.

**Frontend — `apps/frontend`**

- One component for a command turn in the transcript, and the wiring that
  picks it over the text part when a descriptor is present.
- Clicking it opens the existing prompt panel on the turn's own stored text.
- Translations, `fr` and `en`.

**Out of scope**

The `/` trigger, the menu, the placeholder and the Help Center pages: they
belong to the slice that makes the feature reachable, which is where a user
first needs to be taught it exists.
