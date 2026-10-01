## 1. Control plane

- [x] 1.1 Add the `prompt_favorite` model and a linear Alembic migration on the current head; verify `alembic heads` (one head) and a real `alembic upgrade head`.
- [x] 1.2 Add the favorite store (add, remove, list ids for a user among prompt ids, delete for a user on a team, delete all for a user) with unit tests.
- [x] 1.3 Add `PUT` / `DELETE /teams/{team_id}/prompts/{prompt_id}/favorite` (`CAN_USE_TEAM_AGENTS`, idempotent, `404` for a prompt outside the team) and `is_favorite` on `PromptSummary` and `ContextPromptSummary`; cover them in route tests.
- [x] 1.4 Delete favorites in `remove_team_member` (that team's prompts) and `delete_user` (all); cover both in tests.
- [x] 1.5 Regenerate the control-plane OpenAPI and the frontend client; update `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.6 with a dated entry.

## 2. Frontend

- [x] 2.1 `PromptCard`: star `IconButton` next to the more button when `onToggleFavorite` is passed (outline / filled `warning`, tooltip, `aria-pressed`); optimistic toggle with rollback and toast.
- [x] 2.2 Shared `FavoritesFilterChip`: neutral with a filled `warning` star at rest; `warning` fill with `on-warning` star and label when active.
- [x] 2.3 Prompts page: chip first in the filter row, always visible, AND with the category; empty state.
- [x] 2.4 Chat prompt panel: search field and chip on one row in both tabs (category `Select` unchanged below), AND logic, empty state.
- [x] 2.5 English and French strings; tests for the tile toggle, the chip and both filters.

## 3. Documentation and verification

- [x] 3.1 Help Center Prompts page, fr and en.
- [x] 3.2 English migration note (schema migration, no operator action).
- [x] 3.3 Run root `make code-quality`, frontend and control-plane `make test`, `make migration-check`, `openspec validate --strict`, `/code-review`; record the results here.
- [ ] 3.4 Verify in the UI: toggle from both surfaces, both filters, light and dark themes, leaving a team.

Verification (2026-10-01): root `make code-quality` passed all 16 modules (global `uv`
override); control-plane `make test` 1,450 passed; frontend `make test` 3,166 passed,
7 skipped, 4 failed — all in `useChatSse.test.tsx` (first-turn `ask_user`), which fail
identically on `swift` and are unrelated; `alembic heads` one head, `alembic upgrade
head` on the local Postgres, `make db-check-sqlite` (upgrade, check, downgrade) passed;
`make migration-check` accepted 1 new note; `openspec validate --strict` passed. An
independent review found no blocking issue; its refetch-flicker and double-click
findings are fixed. Task 3.4 (UI check) awaits the developer.
