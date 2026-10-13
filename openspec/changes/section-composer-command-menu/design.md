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

- Skill availability and the typed-command precedence are untouched. The
  empty states, the filter and the inline prompt token were left alone at
  first and changed after the owner's review of the feature (see "Owner review
  of the commands feature").
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
   and `onFocusEntry`, so the hook's flat `activeIndex` and arrow-key navigation need
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
   `useId` plus the source name. Every header carries its full label in
   `title`, since the visible text may be truncated (one code path for the
   three headers; only the team one is long enough to need it in practice).
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
   `chatbot.commandMenu.sources.personal` and `.team` first stayed for the
   inline token hint; they were removed later, when the hint took the section
   wording (see "Owner review of the commands feature").
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

### Shape of the delta

The requirement "ReAct slash commands combine platform skills and two prompt
libraries" is REMOVED and re-ADDED under a name without "ReAct", rather than
MODIFIED: `openspec validate --strict` refuses a MODIFIED requirement that
drops a scenario of the main spec, which would have kept two scenario names
that no longer describe the behaviour. Every scenario is carried over.

### Menu rows (added after the first owner check)

Rows lost their inner gap and the skill argument hint; the description is one
line with an ellipsis and the row's `title` gives it in full (it replaced the
"provided by the platform" hint, which the section heading now says). Headings
sit on a `--surface-container-high` band with `--radius-xs` in
`--on-surface-retreat`; prompt and skill tiles share `--secondary-container`. The arrow keys
clamp at both ends instead of wrapping.

### Token containers

One stylesheet, `SkillBadge.module.css`, already dressed the composer widgets
and the sent skill badge. `.badge` becomes the container (secondary pair,
`--radius-xs`, horizontal `--spacing-2xs` padding only) for prompts and skills
alike: the owner settled on one colour for every command, so the two differ by
their icon only. The components still set `data-kind` (`prompt` / `skill`),
which the tests select on and which carries no style, and
`data-surface="bubble"` adds an inset `--secondary` hairline (same hue as the bubble; the neutral outline read poorly on it). No custom
property is added. `CommandTurn` (the sent prompt) drops
its own `--info` slug styles and reuses `.badge`. The composer-only
`.promptToken` class is deleted.

The hairline exists because the user bubble is `--secondary-container`, the
fill of every container, which would be invisible on it. The owner confirmed
it. It is a `box-shadow`, so the container's box and the line height do not
change.
Alternative: a different fill inside the bubble. Rejected: it would break
"same colours in the composer and in the message".

### Slash on every name

Skills used to show a bare name where prompts showed `/name`. The slash is now
part of the displayed text in the three renderers (menu row, composer widgets,
`SkillBadge`); nothing else changes: the document still holds `/name`,
`data-skill-name` and the accessible labels keep the bare name, and offsets and
atomic ranges are untouched. `selectedSkillText` no longer re-inserts a slash
in a copied selection, since the badge's own text has it; it still serialises
any selection touching a badge, to drop icon glyphs and avoid line breaks
around the badge's flex box. Kept bare on purpose: the skill panel title
(`Skill: name`), the "Skill loaded" trace row and the skill usage table, which
name a skill in prose or as data rather than as something to type.

### Caret in the empty composer

In an empty document CodeMirror's `placeholder()` renders
`<img.cm-widgetBuffer><span.cm-placeholder contenteditable=false>` inside the
line, and the selection sits before both. The native caret is then drawn
against a zero-width image of `1em` aligned to the text top and an
`inline-block`, instead of plain text: its size and paint order are whatever
the engine does next to such boxes. A first attempt only lowered the
placeholder's paint order (`z-index: -1`); the owner still saw the caret
partly hidden and cut at the bottom in Firefox, so it was removed.

The extension is dropped. The placeholder is a separate `aria-hidden` span,
rendered by the component while the value is empty, in the same grid cell as
the editor and under it, with the line's inset, font and line height. The
empty line holds only its `<br>`, as in any empty editable; `aria-placeholder`
is set on the content element as the extension did. Sharing a grid cell rather
than absolute positioning keeps a long placeholder wrapping and sizing the
field as before. Checked separately: the line box is 24px and the Geist font
needs 21px (ascent 16, descent 5), so the row's `overflow: hidden` does not
clip a caret sized from the font.

The argument hint stays an inline widget after its token: it is a plain
inline span, not an inline-block, and normally follows the space typed after
the token.

### Tokens as one block

The token ranges are declared as `EditorView.atomicRanges` next to the replace
decorations, so caret motion and selection take a token whole. Backspace and
Delete get a small key binding ahead of the default keymap: when the caret
touches a token it removes the whole `/name`, plus the following space when a
space (or a line start) already precedes the token. Elsewhere it declines and
the default applies. The earlier comment explained that ranges were left
non-atomic so that editing one character dropped recognition; that path still
exists for programmatic edits, it is just no longer reachable from the
keyboard inside a token.

### Owner review of the commands feature

Decisions taken by the owner after an audit of the feature, and how each one
is built.

**Enter inserts, it never sends.** `Enter` in the open menu calls the same
completion as `Tab` and a click. The direct "run from the menu" path is
deleted: `run` now has one caller, the ordinary submit, which already resolved
a picked prompt by its pinned id and owning team and builds the same
`TurnCommand`. The scope and skill checks `run` repeated are removed, since
submit makes them first. The only difference in what is sent is the trailing
space completion adds to `draft_text`, as `Tab` then `Enter` always did.

**Search inside names.** The filter was already on the command name only. It
becomes a case-insensitive substring match, applied source by source (team,
personal, platform) so the flat list stays grouped like the sections; inside a
source, names starting with the text come first, then the others, each in
catalog order. `commandQueryOf` opens the menu in the middle of a message when
some name contains the text, where it required a name starting with it, and
accepts upper case.

**Initial focus: the first row shown.** Alternative: focus the first name that
starts with the text, wherever its section is. Rejected: the focus would jump
between sections from one keystroke to the next, and the row under it would
no longer be the one at the top. "First row" needs no explanation.

**Hand-typed recognition stays case-sensitive.** `/Resume` typed in full is
not turned into `/resume`. Recognition is an exact comparison between the
document text and the name in four places (the token regex, the selection
tracking, recall, the sent bubble), and the typed text is what is stored in
`draft_text` and sent to the agent with the skill names. Accepting another
case would mean either rewriting what the user typed or teaching each of those
places, and the runtime, to compare loosely. Not a small change, so it is left
out; the menu covers the need, since `/Res` lists `/resume` and picking it
inserts the exact name.

**Empty states.** The menu takes one `empty` reason instead of
`teamHasCommands`: `loading` while a catalog it reads is in flight without
data, `none` when nothing exists, `noMatch` otherwise. Keys: `loading` and
`none` added, `noneInTeam` removed (its text was only true in a team).

**Run errors.** `onResolveError` carries a reason. `stale`: the pick's scope
changed, the picked prompt is no longer in a catalog that has answered, or its
read answers 403 or 404. `unreadable`: any other read failure, an empty prompt
text, or a catalog that has not answered. Key `runErrorStale` added;
`runErrorDetail` keeps the retry wording.

**Token hint.** The composer token's hint builds its source line from the
`sections.*` keys with the team's name, passed with the token.
`sources.personal` and `sources.team` are deleted.

**Prompt preview.** `PromptWidget` renders a button when it is given an
`onOpen`, with the shared `.action` hover and focus styles; it stays an inert
span otherwise (hosts that give no preview). The page keeps one stable
`onOpen`, so the widget is not rebuilt on each keystroke. A new drawer kind
carries the prompt's id, team, command and name; `CommandPromptPanel` gains an
optional `status` for loading and error. The text comes from the page's own
lazy prompt-detail query, triggered on opening and not served from cache, so
the panel shows the prompt as it is now. Alternative: a second panel
component. Rejected: same shell, same header, one more file.

**Prompt and skill with the same name: not changed.** The request was to make
a hand-typed name resolve in menu order (team prompt, personal prompt, then
skill) whatever follows it. It is left as it was and reported to the owner,
because it runs against a requirement this spec states twice ("typing/paste
retains existing delimited-skill precedence", "complete delimited skill names
take precedence for typing/paste") and is not a small change: a delimited
skill name gets a skill selection as soon as it is typed, which the token
rendering, undo, recall and submit all read, and that selection is created
before the prompt catalogs are known to have answered.

## Risks / Trade-offs

- [Searching inside names opens the menu on more text typed after a space and
  a slash, for example a path fragment that happens to sit inside a command
  name; Enter would then insert that command instead of sending] → same risk
  as before with names starting with the text, slightly wider; `Esc` closes
  the menu and nothing is ever sent by the menu any more.
- [A user used to running a prompt with one Enter now needs two] → decided by
  the owner, and said in the Help Center.
- [A catalog whose read failed for good shows "no command" or the rows of the
  other catalogs, not an error] → unchanged; only an in-flight read shows the
  loading line.

- [Removing the gate also removes the page's agent-templates request, whose
  only reader was the gate] → one request less per chat page; nothing else in
  `ManagedChatPage.tsx` uses it.
- [The caret could only be looked at in headless Chrome; Firefox does not
  paint the caret in a headless capture] → the fix removes what the caret was
  drawn against rather than tuning it; the owner check covers Firefox.
- [With exactly `/name` and no trailing space, the caret still sits between the
  token and the argument hint, next to CodeMirror's buffer image] → rare (the
  completion adds a space); left for the owner check.
- [Clicking next to a token and mouse selection were not exercised in a
  browser] → they rely on CodeMirror's own handling of atomic ranges.
- [A token keeps its full colours in a disabled composer] → unchanged from
  before (it kept `--primary`); left for the owner check.
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
