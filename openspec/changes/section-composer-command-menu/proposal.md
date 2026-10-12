## Why

The slash command menu above the chat composer shows one flat list under a
single header, tells sources apart with a label on every row, and offers
personal-space commands only with ReAct agents. It is hard to scan, and a user
talking to any other agent kind cannot reach their own commands.
Tracked in GitHub issue #3073.

## What Changes

- The menu is split into sections, each with its own header, always in this
  order: the conversation's team (`Équipe « <name> »` / `Team "<name>"`), the
  user's personal space (`Espace personnel` / `Personal space`), platform skills
  (`Skills plateforme` / `Platform skills`).
- A section with no entry, or no match for the typed text, is hidden together
  with its header.
- Personal-space commands are offered whatever the agent kind. The ReAct-only
  gate is removed. Platform skills keep whatever availability they have today.
- A personal-space conversation shows a single commands section, the personal
  one (no second fetch, as today).
- A command name present in both the team and the personal space shows in both
  sections. Typed without picking a row, the team's command still wins
  (unchanged).
- Headers are no longer uppercased; a long team name is truncated with an
  ellipsis on one line.
- The per-row source label is removed from the menu rows; the headers replace
  it. The hover hint of an inline prompt token in the composer keeps its
  source wording.
- Keyboard navigation stays one continuous list across sections.

No **BREAKING** change. Frontend only: no API, data, configuration or migration
change, and no new CSS custom property.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: the requirement "ReAct slash commands combine
  platform skills and two prompt libraries" is renamed and modified (personal
  commands for every agent kind, sources shown by section instead of per-row
  labels), and a requirement is added for the sectioned menu.

## Impact

- `apps/frontend/src/rework/components/shared/molecules/CommandMenu/CommandMenu.tsx`
  and `CommandMenu.module.css`: sections, headers, no row source label.
- `apps/frontend/src/rework/components/pages/ManagedChatPage/useComposerCommands.ts`:
  the `includePersonalCommands` parameter is deleted; every entry carries its
  source.
- `apps/frontend/src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`:
  no ReAct gate, team name passed to the menu.
- `apps/frontend/src/locales/{fr,en}/translation.json`: four keys added, three
  removed (see design.md).
- Tests: `useComposerCommands.test.tsx`, `ManagedChatPage.test.tsx`, new
  `CommandMenu.test.tsx`.
- Docs: `docs/swift/ux/COMPONENT-UX.md` (`CommandMenu`), Help Center
  `features/commands.md` (fr and en), migration note
  `docs/swift/ops/migrations/3073-composer-command-menu-sections.md` (impact
  none).
