## Why

A message can call several platform skills but only one prompt command: once a
prompt is in the composer, the slash menu stops offering prompts, and a second
`/name` typed by hand is sent to the agent as plain text. The owner decided
that prompt commands compose like skills, in the same pull request as the
sectioned command menu. Tracked in GitHub issue #3073.

## What Changes

- The slash menu keeps offering prompt commands after a first one is in the
  message. Each prompt command is its own token in the composer: one block of
  text, with its own preview.
- On send, every prompt is read and its text takes the place of its command,
  in the order of the message. If any one of them cannot be read, nothing is
  sent and the error names that command.
- The command descriptor of a turn gains an optional list, `prompts`, with one
  entry per prompt command: its identity, where it sits in the typed line and
  where its text sits in the text that was sent. The existing single fields
  stay and describe the first prompt.
- A sent message shows one badge per prompt command, at its place. Clicking a
  badge opens that prompt's own text, no longer the whole message: the user's
  own words stop appearing under the prompt's name.
- Recalling a sent message restores every prompt command with its identity.
- A message holds at most 16 prompt commands.
- The two run errors name the command they are about.
- A conversation written before this change renders exactly as today.

Not **BREAKING**: the list is additive and optional on every hop. One
deployment order avoids a cosmetic degradation (see design.md, "Mixed
versions").

Three points were decided by the owner as proposed (design.md, "Owner
decisions"); each is its own requirement so that changing it later is a small
edit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: requirements are added for several prompt commands
  in one message (menu, tokens, expansion on send, the descriptor list, the
  sent badges and their panel, recall, hand-typed names, compatibility with
  single-prompt turns) and for the three owner decisions. No
  existing requirement of the main spec is modified; the sentences of the
  in-flight `section-composer-command-menu` delta that this change supersedes
  are listed in design.md.

## Impact

- `libs/fred-sdk/fred_sdk/contracts/context.py`: `TurnCommandPrompt`, and
  `TurnCommand.prompts`.
- `libs/fred-core/fred_core/history/history_schema.py`:
  `CommandPromptDescriptor`, and `CommandDescriptor.prompts`.
- `libs/fred-runtime`: no logic change expected (`_turn_command` already
  validates the whole descriptor); tests, and the regenerated `openapi.json`.
- Control plane: not on the path. The browser sends the turn to the runtime pod
  and reads history from it; `controlPlaneOpenApi.ts` is not regenerated.
- Frontend: `runtimeOpenApi.ts` (regenerated), `useComposerCommands.ts`,
  `useComposerRecall.ts`, `ManagedChatPage.tsx`, `InlineSkillInput.tsx`,
  `UserMessage.tsx`, `CommandTurn.tsx`, `UserTurn.tsx`,
  `ConversationThread.tsx`, `utils/skillInvocation.ts`, locales, and their
  tests.
- No database migration: the descriptor is JSON inside
  `session_history.metadata_json`.
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` (new dated entry in section 8),
  `COMPONENT-UX.md`, Help Center `features/commands.md` (fr and en), and the
  pull request's migration note, whose impact goes from `none` to `minor`.
