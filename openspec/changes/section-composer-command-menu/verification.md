## Verification

Run from `apps/frontend` on 2026-10-13, branch
`feat/composer-command-menu-sections`.

| Check | Result |
| --- | --- |
| `npx tsc --noEmit -p .` | exit 0 |
| `npx eslint` on the 11 touched `.ts`/`.tsx` files | exit 0, no warning |
| `npx prettier --check` on the 19 touched frontend files | all formatted |
| `npx vitest run` (full suite) | 329 files passed, 1 skipped; 3960 tests passed, 7 skipped |
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
bubble. In Pebble light `--primary-container` and `--secondary-container` have
the same value, so prompt and skill containers differ there by icon only.

Caret: reproduced the empty editor (CodeMirror, same extensions and the
editor's own rules) in headless Chrome. The caret sits on the left edge of the
placeholder's first glyph; in Chrome it was already painted in front, and the
rendering with the fix is pixel-identical (same placeholder position, 24px
field). Not seen: Firefox, which does not paint the caret in a headless
capture, and the running app, which needs a signed-in session.

Observed and left as is, for the owner to decide: tokens are not atomic. An
arrow key next to a token moves one hidden character at a time (one press from
the end of `/meeting-minutes` goes from offset 23 to 22 with nothing moving on
screen); Backspace right after a token removes one hidden character and the
token turns back into raw `/meeting-minute` text; Delete right before it
removes the slash and leaves the bare name; select-all then delete empties the
field correctly, and undo restores the token.

## Divergence from the plan

- The spec delta uses REMOVED plus ADDED instead of RENAMED plus MODIFIED, to
  get scenario names that match the behaviour (see design.md, "Shape of the
  delta").
- Every section heading carries its label in `title`, not only the team one.
- Each section also exposes its source as a `data-source` attribute, used by
  the tests.
