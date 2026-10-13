## Verification

Run from `apps/frontend` on 2026-10-13, branch
`feat/composer-command-menu-sections`.

| Check | Result |
| --- | --- |
| `npx tsc --noEmit -p .` | exit 0 |
| `npx eslint` on the 11 touched `.ts`/`.tsx` files | exit 0, no warning |
| `npx prettier --check` on the 19 touched frontend files | all formatted |
| `npx vitest run` (full suite) | 329 files passed, 1 skipped; 3968 tests passed, 7 skipped |
| `openspec validate section-composer-command-menu --strict` | valid |
| `scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 new declaration |

Proven by tests: section order and headings, hidden empty and unmatched
sections, team name and its fallback, group labelling, flat option index and
focus across sections, no row source label (`CommandMenu.test.tsx`,
`useComposerCommands.test.tsx`); the personal commands read is no longer tied
to the agent's kind (`ManagedChatPage.test.tsx`).

Not proven by tests: the visual result (sentence-case heading, ellipsis on a
long team name, both themes) and the fr/en wording in the running app. These
are task 6.4, the owner check.

## Token containers and caret

Proven by tests: the composer widgets and the sent badges carry their kind
(`prompt` / `skill`), only sent ones carry the bubble variant
(`InlineSkillInput.test.tsx`, `UserTurn.test.tsx`); no test was removed, and
the full suite count is unchanged because assertions were added to existing
tests.

Seen in a rendered sample (the stylesheet's own rules on a static page,
headless Chrome, values of Pebble light, Pebble dark and Cloud light): a line
with a prompt and a skill container measures 24px, like a plain line, in the
composer and in the bubble; the hairline separates both containers from the
bubble. That sample predates the owner's decision to use one colour, the
secondary container, for prompts and skills: they now differ by icon only in
every theme, and the hairline in the bubble is a confirmed decision.

Caret, first attempt (paint order only): pixel-identical in headless Chrome,
where the caret was already in front; the owner then reported no change in
Firefox, so it was replaced.

Caret, current fix (placeholder outside the editable line), reproduced with
CodeMirror and the editor's own rules in headless Chrome:

- the empty line's content is `<br>` only (it was a buffer image, the
  placeholder span and `<br>`);
- line, editor and row are 24px high, as before;
- the placeholder text is at the same pixels: the only difference between the
  two captures is the caret column;
- the caret goes from 24px, flush with the row's top and bottom edges and
  touching the first glyph, to the ordinary 22px text caret.

Also measured: Geist at 16px has ascent 16 and descent 5 (21px) in a 24px
line, so the row's `overflow: hidden` cannot clip a font-sized caret.

Not seen: the caret in Firefox. Headless Firefox does not paint it, in a plain
`--screenshot` or through its automation port, so there is no direct evidence
for the owner's browser; and the running app, which needs a signed-in session.

Tokens as one block, proven by tests (`InlineSkillInput.test.tsx`,
`useComposerCommands.test.tsx`): one arrow press crosses a token both ways; a
shift-selection takes it whole; Backspace right after and Delete right before
turn `Before /meeting-minutes after` into `Before after` with the caret where
the token was, and undo restores text and token; Backspace elsewhere removes
one character; of two adjacent tokens each is removed alone
(`/review /meeting-minutes notes` → `/review notes` → `notes`) and the command
menu stays closed; a prompt token removed whole comes back through undo with
its selection identity and redo removes it again.

Hand-typed tokens (owner report: Backspace "went inside" a typed token): a
prompt typed by hand has no selection behind it and was shown only while text
followed it, so removing the trailing space un-rendered it and the next
Backspace edited raw text. Fixed in `useComposerCommands.ts`; a typed skill
was not affected. `useComposerCommands.test.tsx` now types a skill and a
prompt one character at a time, at the start and in the middle of a draft,
with and without text after: no token while the name is being typed
(Backspace edits one character), then Backspace down to the token keeps it,
one arrow press crosses it, Backspace removes it whole, and Delete before it
does the same.

Menu on a token at the end of the draft (owner decision: always closed): the
panel now closes on any rendered prompt token, as it did for skills.
`useComposerCommands.test.tsx` covers a picked and a typed prompt: Backspace
on the trailing space keeps the token and the menu closed, a space or text
typed again keeps it closed, and ` /re` opens the menu with `review` only.
The recall test host in `useComposerRecall.test.tsx` was rewired to
`composerValue` / `onComposerChange`, as `ManagedChatPage` wires the field; it
passed the raw `input` / `setInput`, which kept a recalled selection alive
across edits and so showed a token the page would not. Its assertions are
unchanged: a recalled command keeps the menu shut, and editing it opens it.

Not proven: clicking on either side of a token and mouse selection (no layout
in the test environment), and the caret sitting between a token and the
argument hint when the draft is exactly `/name`.

Slash on every name, proven by tests: menu labels read `/search`, `/summary`,
`/meeting-minutes`, `/review` (20 label expectations updated in
`useComposerCommands.test.tsx`); composer tokens read `/summary` and
`/meeting-minutes` over an unchanged document; sent messages read
`Before /meeting-minutes after`; a selection-copy of a skill badge, of its
name alone and of the whole message gives one slash; legacy `/skill name`
turns still display as `/name` (existing `UserTurn.test.tsx` cases). The full
suite count is unchanged at 3968: expectations were updated, none removed
except one partial-name selection assertion that no longer has a meaning.

## Owner review of the commands feature

Run from `apps/frontend` on 2026-10-13, after tasks 8.1 to 8.8.

| Check | Result |
| --- | --- |
| `npx tsc --noEmit -p .` | exit 0 |
| `npx eslint` on the 12 touched `.ts`/`.tsx` files | exit 0, no warning |
| `npx prettier --check` on the 18 touched frontend files | all formatted |
| `npx vitest run` (full suite) | 329 files passed, 1 skipped; 3982 tests passed, 7 skipped (3968 before) |
| `openspec validate section-composer-command-menu --strict` | valid |
| `scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 new declaration |

Proven by tests:

- Enter (`useComposerCommands.test.tsx`): Enter on a prompt row gives
  `/summary `, closes the menu and calls neither send path; the second Enter
  sends the prompt's text with the full descriptor (`command`, `prompt_id`,
  `prompt_name`, `draft_text`, `draft_command_offset`); picking with Enter and
  with Tab in `Avant /su` produce two identical calls; Shift+Enter is left to
  the composer; the personal homonym is sent from its own library when picked
  with Tab, a click or Enter. Five existing cases that ran a prompt with one
  Enter now press it twice.
- Search (`useComposerCommands.test.tsx`): `/MAR` lists `/summary`, `see /Ear`
  lists `/search`, `/cher` (the prompt's name and description) matches
  nothing; with five prompts and two skills, `/sum` gives `/pre-sum`,
  `/big-sum` then `/sum-up`, `/sum`, `/my-sum` then `/summarize`, `/resume`,
  with the focus on `/pre-sum`.
- Empty states (`CommandMenu.test.tsx`, `useComposerCommands.test.tsx`): each
  of the three lines as a status; a catalog in flight shows the loading line
  for `/` and for `/zzz`, never "no command" or "no match"; rows of a catalog
  that answered are shown meanwhile; once everything answered empty, the "no
  command" line.
- Run errors (`useComposerCommands.test.tsx`): `stale` after a team, agent or
  personal-space change, for a prompt gone from its catalog, for a recalled
  prompt that no longer exists and for a 403 or 404 read; `unreadable` for a
  thrown read and for a typed personal command while the team's catalog is
  pending.
- Token hint and preview (`InlineSkillInput.test.tsx`,
  `ManagedChatPage.test.tsx`): the token is a `button` with the shared action
  class and the "open the prompt" label; its hint's second line is the
  personal-space key, the team key with a name, the fallback without one; a
  click calls the preview and neither sends nor edits; one arrow press still
  crosses it; without a preview handler it stays an inert group. On the page,
  the click reads the prompt with its id and team, the panel shows the loading
  line, then name, command and text in that order, then the error line when
  the read fails, and a second click closes it with a single read made.
- Prompts page (`PromptsPage.test.tsx`): the created and failed-save toasts
  use their keys.

Not proven: nothing was looked at in a browser. The wording of the new fr and
en strings, the hover and focus look of the prompt token, the panel's layout
and the loading line's timing are for the owner check (task 6.4). No test
drives a real pointer on the CodeMirror token; the click is dispatched on the
widget's element.

Not done, reported to the owner: a hand-typed name shared by a prompt and a
platform skill still resolves as before (see design.md), and a command typed
in full in another case is not recognised.

## Divergence from the plan

- The spec delta uses REMOVED plus ADDED instead of RENAMED plus MODIFIED, to
  get scenario names that match the behaviour (see design.md, "Shape of the
  delta").
- Every section heading carries its label in `title`, not only the team one.
- Each section also exposes its source as a `data-source` attribute, used by
  the tests.
