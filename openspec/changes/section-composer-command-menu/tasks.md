## 1. Hook and page

- [x] 1.1 In `useComposerCommands.ts`, delete the `includePersonalCommands` parameter (and its place in the scope key): always read the personal library unless `personalTeamId` is missing or equals `teamId`, and always set `source` on prompt and skill entries; verify with the updated hook tests of 4.1
- [x] 1.2 In `CommandMenu.tsx`, make `source` required on `CommandMenuEntry`; verify `npx tsc --noEmit -p .` reports no error
- [x] 1.3 In `ManagedChatPage.tsx`, drop `includePersonalCommands: agentCategory === "react"` and pass `teamName={team?.name}` to `CommandMenu`; delete `agentCategory` and the agent-templates query, which nothing else in the page reads; verify with the updated page test of 4.3

## 2. Menu

- [x] 2.1 In `CommandMenu.tsx`, render one `role="group"` per non-empty source in the order team, personal, platform, each `aria-labelledby` its own header, rows keeping their index in `entries` for `optionId`, `aria-selected`, `data-active`, `onActivate` and `onFocusEntry`; verify with `CommandMenu.test.tsx` (4.2)
- [x] 2.2 Add the `teamName` prop: team header from `chatbot.commandMenu.sections.team` with the name, `sections.teamFallback` when the name is missing, full label in `title` of each header; verify with `CommandMenu.test.tsx`
- [x] 2.3 Remove the row source label and the header-by-kind logic; verify no `sources.` key and no `promptsSection` or `menuTitle` key remains in `CommandMenu.tsx` (grep)
- [x] 2.4 In `CommandMenu.module.css`, remove `text-transform` and `letter-spacing` from `.groupTitle`, add one-line ellipsis truncation, delete `.sourceLabel`; verify no new custom property is introduced (diff review)

## 3. Locales

- [x] 3.1 In `locales/fr/translation.json` and `locales/en/translation.json`, add `chatbot.commandMenu.sections.{team,teamFallback,personal,platform}` and remove `chatbot.commandMenu.promptsSection`, `chatbot.skills.menuTitle` and `chatbot.commandMenu.sources.platform`, as listed in design.md; verify by grep that no removed key is still read in `apps/frontend/src` and that both files hold the same keys

## 4. Tests

- [x] 4.1 Update `useComposerCommands.test.tsx`: remove `includePersonalCommands` from the `Host` and its call sites, drop the "category" variants built on it, replace the header assertion (about line 249) and the source-label assertions (about lines 1194-1212 and 1314-1319) with section assertions (headers shown, entries per section, single personal section in a personal chat, both `/summary` rows under their section), keep the inline token hint assertion on `sources.*` and the team-precedence cases; verify the file passes
- [x] 4.2 Add `CommandMenu.test.tsx`: section order, hidden empty sections, team name and fallback, `title` on the team header, `role="group"` with `aria-labelledby`, global option ids and active row across sections, no row source label; verify the file passes
- [x] 4.3 Update `ManagedChatPage.test.tsx` ("ReAct slash prompt sources", about line 1150): the personal commands query is not skipped for react, deep, graph, proxy and an unresolved template; verify the file passes

## 5. Docs

- [x] 5.1 Rewrite the behaviour paragraphs of `### CommandMenu` in `docs/swift/ux/COMPONENT-UX.md`: three sections and their headers, no row label, personal commands for every agent kind, sentence-case truncated header; correct the fill token it names to the one the stylesheet uses; verify the section no longer mentions ReAct-only sources or a heading that follows entry kinds
- [x] 5.2 Update the Help Center pages `rework/features/helpCenter/content/fr/features/commands.md` and `en/features/commands.md` ("Lancer une commande" / "Run a command" and the paragraph on mixing prompts and skills): sections instead of labels, personal commands with every agent, no "Deep agents retain their current behavior"; verify fr and en say the same thing in non-technical wording
- [x] 5.3 Add `docs/swift/ops/migrations/3073-composer-command-menu-sections.md` from the template (impact none, configuration none); verify its front matter matches `MIGRATION-NOTE-TEMPLATE.md`

## 7. Menu rows, token containers and caret

- [x] 7.1 Menu rows: no argument hint and no gap, one-line description with the full text in `title`, heading band, prompt and skill tiles in the same secondary container, arrow keys clamped at both ends; verify with `useComposerCommands.test.tsx`
- [x] 7.2 In `SkillBadge.module.css`, make `.badge` a container (secondary pair, `--radius-xs`, horizontal `--spacing-2xs` padding) for prompts and skills alike, with a `data-surface="bubble"` variant (inset `--secondary` hairline); verify no new custom property (diff review) and a 24px line with and without a token in a rendered sample
- [x] 7.3 Set `data-kind` on `SkillWidget` and `PromptWidget` in `InlineSkillInput.tsx` and delete `.promptToken`; verify with `InlineSkillInput.test.tsx`
- [x] 7.4 Set `data-kind` and `data-surface` in `SkillBadge.tsx` and make `CommandTurn` reuse the shared container; verify with `UserTurn.test.tsx`
- [x] 7.5 In `InlineSkillInput.module.css`, paint the placeholder and the argument hint one layer below the editor content; verify in a rendered sample that the caret is in front and nothing moves
- [x] 7.7 Replace CodeMirror's `placeholder()` by an element outside the editable line (same grid cell, `aria-hidden`, `aria-placeholder` on the content) and remove the paint-order rule of 7.5; verify with `InlineSkillInput.test.tsx` and a rendered sample (empty line holds only its line break, placeholder at the same position, 24px field)
- [x] 7.8 Declare the token ranges as atomic and bind Backspace/Delete to whole-token removal with space clean-up; verify with `InlineSkillInput.test.tsx` (arrows, selection, Backspace, Delete, undo) and `useComposerCommands.test.tsx` (two tokens, menu stays closed, undo/redo of a prompt)
- [x] 7.9 Keep a hand-typed prompt token rendered once shown and keep the command menu closed on any rendered token; verify with `useComposerCommands.test.tsx` and `useComposerRecall.test.tsx`
- [x] 7.10 Show the leading slash on every command name (menu rows, composer tokens, sent skill badge) without changing stored text, labels or copy; verify with `useComposerCommands.test.tsx`, `InlineSkillInput.test.tsx` and `UserTurn.test.tsx`
- [x] 7.6 Update `COMPONENT-UX.md` (composer token, sent badges, caret) and this change's artifacts; verify `openspec validate section-composer-command-menu --strict`

## 8. Owner review of the commands feature

- [x] 8.1 Enter on a menu row completes like Tab and a click; delete the run-from-menu path so the ordinary submit is the only sender; verify with `useComposerCommands.test.tsx` (insert then send, same turn as Tab then Enter, Shift+Enter)
- [x] 8.2 Match the typed text inside command names, whatever the case, names starting with it first in each section, focus on the first row; `commandQueryOf` opens mid-message on the same match; verify with `useComposerCommands.test.tsx`
- [x] 8.3 Replace `teamHasCommands` by an `empty` reason (`loading`, `none`, `noMatch`) with the keys `loading` and `none`; verify with `CommandMenu.test.tsx` and `useComposerCommands.test.tsx`
- [x] 8.4 Give `onResolveError` a reason and add `runErrorStale`; verify with `useComposerCommands.test.tsx` (scope change, prompt gone from its catalog, 403/404, failed read, pending catalog)
- [x] 8.5 Build the token hint from the `sections.*` keys with the team name and delete `sources.*`; verify with `InlineSkillInput.test.tsx` and a grep for the removed keys
- [x] 8.6 Move the three save toasts of `PromptsPage.tsx` to `rework.teams.prompts.toasts.*` and reword `form.commandConflict`; verify with `PromptsPage.test.tsx`
- [x] 8.7 Make the composer's prompt token a button opening its prompt in `CommandPromptPanel` (name, command, current text, loading and error lines); verify with `InlineSkillInput.test.tsx` and `ManagedChatPage.test.tsx`
- [x] 8.8 Update the Help Center pages (`commands.md`, `chat.md`, fr and en), `COMPONENT-UX.md` and this change's artifacts; verify `openspec validate section-composer-command-menu --strict`

## 6. Verification

- [x] 6.1 From `apps/frontend`, run `npx tsc --noEmit -p .`; verify it exits 0
- [x] 6.2 From `apps/frontend`, run `npx eslint` and `npx prettier --check` on the touched files; verify both exit 0
- [x] 6.3 From `apps/frontend`, run `npx vitest run` on `useComposerCommands.test.tsx`, `CommandMenu.test.tsx`, `ManagedChatPage.test.tsx` and `InlineSkillInput.test.tsx`; verify all pass, then clean the vitest cache directories left in `/tmp`
- [ ] 6.4 Owner check in the app, in Firefox and Chrome: caret in the empty composer and next to a skill's argument hint, tokens as one block (arrows, Backspace, Delete, shift-selection, click on each side, undo), token containers in the composer and in sent messages (three themes, light and dark), and team chat with a ReAct agent and with a Deep agent (three sections, team name in the header, long name truncated, filtering hides a section, arrows cross sections, both `/summary` rows, typed `/summary` runs the team's), personal-space chat (single personal section), fr and en, light and dark theme, and the inline token hover hint; then Enter on a prompt row and on a skill row (inserts, second Enter sends), search inside names and upper case, the loading and "no command" lines, both run-error toasts, and the prompt token preview (hover, click, keyboard, loading, a deleted prompt)
- [ ] 6.5 Record the verification evidence in this change, then archive it once merged; verify `openspec validate --specs --strict` passes after the archive
