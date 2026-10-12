## Context

See proposal.md for motivation. Current state, read from the code:

- `CommandMenu.tsx` renders one `role="group"` inside the `role="listbox"`. Its
  header is picked from the entry kinds: `chatbot.skills.menuTitle` (skills
  only), `chatbot.commandMenu.ariaLabel` (mixed) or
  `chatbot.commandMenu.promptsSection` (prompts only). Each row ends with
  `chatbot.commandMenu.sources.<source>` when the entry has a `source`.
- `useComposerCommands.ts` already builds the list as team prompts, then
  personal prompts, then skills, and filters each part in place, so sources
  are contiguous slices of one array. `source` is only set when
  `includePersonalCommands` is true; team prompts are tagged `personal` when
  `personalTeamId === teamId`, and the second fetch is skipped in that case.
- `ManagedChatPage.tsx` passes `includePersonalCommands: agentCategory === "react"`
  and already holds the conversation's team:
  `team = isPersonalTeam ? activeTeam : fetchedTeam` (`useFrontendBootstrap` /
  `useGetTeamQuery`), a generated `Team` with a `name`.
- i18n runs with `escapeValue: false`, so a team name interpolates as is.

## Goals / Non-Goals

**Goals:**

- Sections derived from the existing `source` of each entry, with no change to
  list order, filtering, option ids or keyboard handling.
- Remove more than is added: the ReAct gate, the header-by-kind logic, the row
  source label and their keys.

**Non-Goals:**

- Skill availability, the `/skill ` filter, the empty states (`noMatch`,
  `noneInTeam`) and the typed-command precedence are untouched.
- No change to the inline prompt token in the composer beyond what removing the
  gate implies (see Risks).
- No new CSS custom property, no API or generated client change.

## Decisions

1. **Delete `includePersonalCommands` instead of passing `true`.** The hook
   always reads the personal library (still skipped when `personalTeamId` is
   missing or equals `teamId`), and every entry always carries a `source`, which
   becomes required on `CommandMenuEntry`. Alternative: keep the parameter and
   pass `true`. Rejected: a parameter with one value is dead code, and it also
   sits in the hook's scope key for nothing.
2. **The menu groups by `source`, keeping the global index.** `CommandMenu`
   walks the fixed order `team`, `personal`, `platform`, and for each takes the
   entries of that source together with their index in `entries`. That index
   still feeds `optionId(index)`, `aria-selected`, `data-active`, `onActivate`
   and `onFocusEntry`, so the hook's flat `activeIndex` and arrow-key wrap need
   no change. A source with no entry renders nothing. Alternative: the hook
   returns pre-built sections. Rejected: it duplicates the list and moves
   indexes into two places.
3. **The team name reaches the menu as a prop from the page.**
   `ManagedChatPage` renders `<CommandMenu {...commands.menu} teamName={team?.name} />`.
   The hook does not need the name and stays unaware of it. Alternative: the
   menu reads the team itself. Rejected: a shared molecule should not fetch.
4. **Name not loaded yet: the header reads `Équipe` / `Team`.** `team` is
   undefined while `useGetTeamQuery` is in flight. A bare label is shown rather
   than empty quotes or a hidden header (minor assumption).
5. **Each section is a `role="group"` with `aria-labelledby` its own header**,
   inside the listbox, as the single group does today. Header ids come from one
   `useId` plus the source name. The team header also carries the full label in
   `title`, since the visible text may be truncated.
6. **Header style.** `.groupTitle` loses `text-transform: uppercase` and its
   `letter-spacing: 0.06em`: that tracking only existed to open up capitals and
   reads as loose in sentence case (minor assumption). It gains one-line
   truncation (`white-space: nowrap`, `overflow: hidden`,
   `text-overflow: ellipsis`). The whole header is truncated, so the closing
   quote goes with the end of a long name. `.sourceLabel` is deleted.
7. **Locale keys**, in `fr` and `en`:

   | Key | Change | fr | en |
   | --- | --- | --- | --- |
   | `chatbot.commandMenu.sections.team` | added | `Équipe « {{name}} »` | `Team "{{name}}"` |
   | `chatbot.commandMenu.sections.teamFallback` | added | `Équipe` | `Team` |
   | `chatbot.commandMenu.sections.personal` | added | `Espace personnel` | `Personal space` |
   | `chatbot.commandMenu.sections.platform` | added | `Skills plateforme` | `Platform skills` |
   | `chatbot.commandMenu.promptsSection` | removed | | |
   | `chatbot.skills.menuTitle` | removed | | |
   | `chatbot.commandMenu.sources.platform` | removed | | |

   `chatbot.skills.menuTitle` is `Skills` in both languages, which does not fit
   the agreed label, and the menu is its only reader: it is replaced rather
   than reworded so the three headers live in one family.
   `chatbot.commandMenu.sources.personal` and `.team` stay for the inline token
   hint in `InlineSkillInput.tsx`, which only ever reads those two.
   `chatbot.commandMenu.ariaLabel` stays as the listbox label; it is no longer
   used as a header.

### Relation to in-flight changes

`add-prompt-command-trigger` (19/20), `add-prompt-command-field` (21/22) and
`add-command-turn-rendering` (17/18) are complete but unarchived: the only
unticked task in each is its own archive step. Their deltas target a
`prompt-commands` capability that does not exist yet in `openspec/specs/`, so
this change cannot MODIFY them and does not edit them.

`add-prompt-command-trigger` states that the menu has "a single section today
titled for the team's prompt library" and offers "only prompts of the active
team". Both sentences were already outdated by the personal and skill sources
recorded in `platform-agent-skills`, and this change makes the first one wrong
too. When that change is archived, its requirement "The menu SHALL be a
sectioned list" has to be reconciled with the section requirement added here
(keep its "every command is offered" part, drop the single-section wording).
This change records its requirements in `platform-agent-skills`, where the
current multi-source behaviour already lives.

### Scenario names kept in the delta

`openspec validate --strict` refuses a MODIFIED requirement that drops a
scenario the main spec has. The scenarios "ReAct team chat offers three
sources" and "Other execution families retain current behavior" therefore keep
their names; the second one now states that other families get the same
personal-plus-team commands, with skill behaviour preserved.

## Risks / Trade-offs

- [Removing the gate also removes the page's agent-templates request, whose
  only reader was the gate] → one request less per chat page; nothing else in
  `ManagedChatPage.tsx` uses it.
- [The inline prompt token's hover hint shows the source only when `source` is
  set, which today means ReAct only] → with the gate gone it shows for every
  agent kind. This follows from offering both libraries everywhere and is
  called out for the owner check.
- [With non-ReAct agents a typed command the team does not hold now falls back
  to the personal library] → intended consequence of the agreed scope; the
  existing precedence and pending-catalog guard apply unchanged.
- [Team prompts are tagged `team` until the bootstrap gives the personal team
  id, so a personal chat could briefly show a team header] → the bootstrap is
  loaded by the shell before the page; no extra guard is added.
- [Homonym rows no longer differ by their own text] → the group label
  (`aria-labelledby`) and the visible header tell them apart.
- [`useComposerCommands.test.tsx` passes `includePersonalCommands` in about 25
  places and has "category" variants built on it] → the test rework is larger
  than the code change; it is mechanical.

## Migration Plan

None. Deploy normally; rollback is a revert of the frontend commit.
