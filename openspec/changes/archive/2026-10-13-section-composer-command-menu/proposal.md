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
  it. The hover hint of an inline prompt token in the composer names its
  source with the same wording as the headers.
- Keyboard navigation stays one continuous list across sections and stops at
  the first and last row instead of wrapping.
- Menu rows are tighter: name above a one-line description cut with an
  ellipsis (full text on hover), no argument hint in the menu, section headings
  on a filled band, prompt and skill icons on the same secondary container tile.
- Inline tokens in the composer and badges in sent messages become small
  containers, one colour for all (the secondary container): prompts and
  platform skills differ by their icon only, and the line height is unchanged.
- In the empty composer the caret is always drawn in front of the placeholder.
- Enter on a menu row inserts the command like Tab and a click, and sends
  nothing; a second Enter sends.
- The menu searches inside command names, whatever the case, names starting
  with the typed text first in each section.
- The empty menu says the commands are loading while they are, and its "no
  command" line holds in a team and in the personal space.
- A command that cannot run says whether to choose it again or to retry.
- The prompt token in the composer opens a preview of its prompt in the chat
  side panel.

No **BREAKING** change. Frontend only: no API, data, configuration or migration
change, and no new CSS custom property.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: the requirement "ReAct slash commands combine
  platform skills and two prompt libraries" is replaced by one without the
  ReAct condition (personal commands for every agent kind, sources shown by
  section instead of per-row labels); requirements are added for the sectioned
  menu, the token containers, the caret, picking a row, the search, the empty
  states, the run errors and the prompt preview; "Web users can require a skill for
  their request" is modified where it described the token as unfilled and the
  argument hint as shown in the suggestions.

## Impact

- `apps/frontend/src/rework/components/shared/molecules/CommandMenu/CommandMenu.tsx`
  and `CommandMenu.module.css`: sections, headers, no row source label.
- `apps/frontend/src/rework/components/pages/ManagedChatPage/useComposerCommands.ts`:
  the `includePersonalCommands` parameter is deleted; every entry carries its
  source.
- `apps/frontend/src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`:
  no ReAct gate, team name passed to the menu.
- `apps/frontend/src/locales/{fr,en}/translation.json`: keys added and removed
  (see design.md).
- `shared/molecules/CommandPromptPanel/CommandPromptPanel.tsx` (preview states)
  and `PromptsPage.tsx` (translated save toasts).
- `shared/molecules/SkillBadge/` (stylesheet shared by composer tokens and sent
  badges), `shared/molecules/CommandTurn/`, and
  `shared/molecules/RichInputField/InlineSkillInput.tsx` + `.module.css`.
- Tests: `useComposerCommands.test.tsx`, `ManagedChatPage.test.tsx`, new
  `CommandMenu.test.tsx`, `InlineSkillInput.test.tsx`, `UserTurn.test.tsx`.
- Docs: `docs/swift/ux/COMPONENT-UX.md` (`CommandMenu`), Help Center
  `features/commands.md` (fr and en), migration note
  `docs/swift/ops/migrations/3073-composer-command-menu-sections.md` (impact
  none).
