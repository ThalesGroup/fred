## Verification

Run from `apps/frontend` on 2026-10-13, branch
`feat/composer-command-menu-sections`.

| Check | Result |
| --- | --- |
| `npx tsc --noEmit -p .` | exit 0 |
| `npx eslint` on the 6 touched `.ts`/`.tsx` files | exit 0, no warning |
| `npx prettier --check` on the 11 touched frontend files | all formatted |
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

## Divergence from the plan

- The spec delta uses REMOVED plus ADDED instead of RENAMED plus MODIFIED, to
  get scenario names that match the behaviour (see design.md, "Shape of the
  delta").
- Every section heading carries its label in `title`, not only the team one.
- Each section also exposes its source as a `data-source` attribute, used by
  the tests.
