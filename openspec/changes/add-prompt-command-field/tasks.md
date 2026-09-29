## 1. Data model and migration

- [x] 1.1 Add the nullable `command` column to `PromptRow` in
      `models/prompt_models.py` with a partial unique index on
      `(team_id, command)` restricted to `command IS NOT NULL`; verify the
      model declares the index and that `uq_prompt_team_name` is untouched.
- [x] 1.2 Generate one Alembic revision re-parented on the backend's current
      head (`alembic heads` must print exactly one), adding the column then the
      index, with a downgrade that drops both; verify `alembic upgrade head`,
      `alembic downgrade -1` and `alembic upgrade head` all succeed against a
      local database.
- [x] 1.3 Carry the field on `PromptRecord` in `prompts/store.py`; verify a
      round-trip store test writes a command and reads it back, and that a
      record with no command reads back as `None`.
- [x] 1.4 Raise a dedicated command-conflict error from the store, sibling to
      `PromptAlreadyExistsError`; verify tests cover a duplicate command in one
      team (raises), the same command in a different team (does not),
      re-saving a prompt with its own command (does not), and several prompts
      with no command coexisting (does not).

## 2. API contract

- [x] 2.1 Add `command` to `CreatePromptRequest` and `UpdatePromptRequest` with
      the `^[a-z0-9_-]{1,64}$` pattern, coercing empty or whitespace-only input
      to `None` before validation; verify tests reject `résumé`, `mon resume`,
      `Summary` and a 65-character value with a 422 naming the field, and
      accept `synthese_v2-bis` and an absent value.
- [x] 2.2 Expose `command` on `PromptSummary` and `PromptDetail`; verify a
      listing and a detail response both carry it for a prompt that has one.
- [x] 2.3 Answer a command conflict with 409 identifying the command as the
      offending field, distinct from the existing name conflict; verify one
      test per conflict kind asserts the two are distinguishable.
- [x] 2.4 Confirm the marketplace projections carry the command through
      inheritance; verify a test reads a published prompt with a command
      through a marketplace surface and finds it.
- [x] 2.5 Add `_next_imported_command` next to `_next_imported_name` in
      `product/service.py`: return the source command unchanged when free in
      the target team, otherwise the first free `{base}-N` from `N=2`, with the
      base trimmed so the result stays within 64 characters; verify unit tests
      cover free (unchanged), taken (`-2`), taken through `-2` (`-3`), absent
      (returns `None`) and a base long enough to need trimming.
- [x] 2.6 Call it from `import_published_prompt_into_team` and copy the result
      onto the new record, with a comment saying why the command is treated
      unlike `category_id`; verify a test imports the same prompt twice into
      one team and finds `summary` then `summary-2`, and that a source with no
      command imports with none.
- [x] 2.7 Keep the concurrent-import race surfacing as a per-team conflict, as
      the name path already does; verify the existing `PromptAlreadyExistsError`
      handler also covers a command collision raised by the index rather than
      turning into a 500.

## 3. Frontend — prompt form

- [x] 3.1 Run `make update-control-plane-api` in `apps/frontend` and commit the
      regenerated `controlPlaneOpenApi.ts`; verify the generated
      `PromptSummary`/`PromptDetail` types carry `command` and that no
      hand-written type duplicates it.
- [x] 3.2 Add the command input to the prompt create/edit form in
      `PromptsPage.tsx`, submitting it through the existing POST and PUT
      mutations; verify a test fills the field, saves, and asserts the value
      reaches the mutation payload.
- [x] 3.3 Filter the input as it is typed — fold an uppercase keystroke to
      lowercase, refuse every other disallowed character, stop at 64; verify
      tests type `S` and see `s`, and type a space, an accented letter and a
      punctuation mark and see the value unchanged.
- [x] 3.4 Show the command field in error with "Label de commande déjà pris par
      un autre prompt d'équipe" when the backend answers 409 on save; verify a
      test drives the conflict and asserts the message lands on that field.
- [x] 3.5 Add the `fr` and `en` translations for the command label, helper text
      and conflict message; verify no key resolves to its own name in either
      locale.

## 4. Frontend — import picker

- [x] 4.1 Render the prompt's own team as selected and not selectable in
      `ImportPromptDialog.tsx` — `checked={isOrigin || selected.has(team.id)}`
      alongside the existing `disabled={isOrigin}`, no overlay; verify a test
      asserts the row reads as checked **and** that confirming does not include
      it in `target_team_ids` — the trap is rendering it checked by adding it
      to the submitted set.

## 5. Close-out

- [x] 5.1 Run `make code-quality` and `make test` in both
      `apps/control-plane-backend` and `apps/frontend`; verify all four pass
      with no new warnings.
- [x] 5.2 Run `/code-review` on the diff and address findings; verify no
      correctness finding remains open.
- [x] 5.3 Write the migration note under `docs/swift/ops/migrations/`, declaring
      the impact and stating that a downgrade loses authored commands; verify
      `make migration-check` passes from the repository root.
- [x] 5.4 Record exact verification evidence in this change, then trim
      `PROMPT-COMMAND-TRIGGER-RFC.md` of what this slice delivered (§2.1 and the
      §2.6 decision) so the RFC keeps only what is still unbuilt; verify the RFC
      no longer describes the field as proposed.
- [ ] 5.5 Archive the change once the implementation has merged; verify
      `openspec/specs/prompt-commands/spec.md` becomes the current capability
      spec.

## Verification evidence

Recorded 2026-09-28, at the commit that closes tasks 1.1–5.4.

**Schema.** `alembic heads` prints exactly one head (`21e235382895`).
`upgrade head` → `downgrade -1` → `upgrade head` all succeed against the local
Postgres; the downgrade leaves no `command` column behind. The index reads
`"uq_prompt_team_command" UNIQUE, btree (team_id, command) WHERE command IS NOT
NULL`, and a direct probe confirms the guarantee: the same command in two
teams is accepted, two null commands in one team are accepted, a duplicate
within one team is refused by that index.

**Backend.** `make code-quality` clean (ruff, import order, format,
basedpyright against the baseline). `make test` → **1380 passed, 8
deselected** — the 8 are the pre-existing `test_team_wiki_store_postgres_
integration.py` cases needing a Postgres on port 5433, untouched by this
change.

**Frontend.** `make code-quality` clean (tsc, prettier, eslint). `make test` →
**2918 passed, 7 skipped, 250 files**, up one file and seven tests from the
branch point.

**Divergence from design.md, resolved in code.** The design said a distinct
store error lets the API "answer 409 with the offending field named" but did
not fix the wire shape. A name conflict and a command conflict are both 409 on
the same route, so the form needs a machine-readable discriminator rather than
prose. Implemented additively: `PromptRequestError` gained an optional `code`,
and `_prompt_error_detail` emits `{"code", "message"}` only when one is set —
every other prompt error keeps the plain-string `detail` its callers already
handle. Locked down by
`test_create_prompt_reports_a_command_conflict_apart_from_a_name_one`.

**Not run.** `/code-review` is a built-in CLI command the assistant cannot
invoke; task 5.2 was carried out as a self-review of the diff. The three
findings it produced — a reused Alembic revision id, `text` shadowed between
the SQLAlchemy helper and the column of that name, and an index-based test
field reader that would silently assert about the wrong input once the form
gained a field — were each fixed before this evidence was written.
