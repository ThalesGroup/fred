## 0. Preconditions

- [x] 0.1 GitHub issue #3042 created and linked in proposal.md; branch `feat/unique-agent-names-per-team` from swift.

## 1. Database

- [x] 1.1 Alembic revision on the current control-plane head: trim names, rename collisions `<name> (n)` by creation order within 255 characters, create the unique index on `team_id, lower(display_name)` (names stored trimmed); downgrade drops the index. Verify: migration test with seeded collisions (case, spaces, an existing `(2)`, a 255-character name); `alembic heads` shows one head and `alembic upgrade head` runs on the local database. Done: `test_migration_renames_duplicates_by_creation_order_then_indexes` (SQLite); `make db-check-heads` one head; `make db-check-sqlite` passed; on a temporary PostgreSQL database `alembic upgrade head` renamed `Équipe RH` / ` équipe rh ` / `ÉQUIPE RH` to `Équipe RH`, `équipe rh (2)`, `ÉQUIPE RH (3)`, the index refused a new `équipe rh `, and the downgrade ran; database dropped. CI `check-migrations-postgres` then flagged `trim` (reflected as `TRIM(BOTH FROM …)`); the index became `lower(display_name)` and `alembic upgrade head` + `alembic check` pass on a temporary PostgreSQL database.
- [x] 1.2 Model: declare the index on `agent_instance`; store raises `AgentNameAlreadyExistsError` on its violation (insert and update). Verify: store tests for both. Done: store tests for create and rename.

## 2. Control plane

- [x] 2.1 Request schemas strip `display_name`; shared `normalize_agent_name`. Verify: schema tests; OpenAPI unchanged (`make generate-openapi` diff empty). Done: schemas strip; OpenAPI changed only by `AgentCopyResult.error_code` (client regenerated).
- [x] 2.2 Enroll, update and duplicate refuse a taken name with `EnrollmentError(409, code="agent_name_conflict")`, the API returning the code; a case-only rename of the same agent is accepted. Verify: service and API tests for each path. Done: API tests (coded 409 on create before any pod call, rename refused, case-only rename accepted, trimmed storage).
- [x] 2.3 Copy: `_copy_name` compares normalised names; one retry on an index violation. Verify: `test_agent_copy.py` cases for a case-only conflict and a simulated race. Done: case-only conflict, duplicate refused before the pod, simulated race.
- [x] 2.4 Importer renames a conflicting agent `<name>_imported-<n>`. Verify: importer test with a conflicting name under another id. Done: `test_import_renames_an_agent_whose_name_is_taken_in_its_team`; reads in the agent import skip autoflush so SQLite does not lock during the phase.

## 3. Frontend

- [x] 3.1 `TeamAgentsPage` passes the other agents' normalised names to `AgentFormModal` and `DuplicateAgentDialog`; a taken name shows its error when the name field loses focus and disables submit until it changes; a server `agent_name_conflict` lands on the same field with the values kept, other errors keep the toast. fr/en key for the message. Verify: vitest for both dialogs (blur warning, case/space variants, own name on edit accepted, submit disabled, server 409 on the field). Done: `AgentFormModal.names.test.tsx`, `DuplicateAgentDialog.test.tsx`, `agentNames.test.ts`; the duplicate dialog opens on the first free `<name> (n)`.

## 4. Docs and close-out

- [x] 4.1 `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated entry on the `display_name` rule and the 409 code; fix the "agent names are not unique" KPI note to say "across teams". Verify: the contract reads consistently. Done: §60 added; `display_name` field and KPI note aligned.
- [x] 4.2 Migration note, impact `minor` (required for a new Alembic revision), with a read-only query listing colliding names. Verify: migration note check valid. Done: `3042-unique-agent-names-per-team.md`, migration note check valid.
- [x] 4.3 Quality gates: control-plane `make code-quality` and `make test`; frontend `npx tsc --noEmit`, `npx prettier --check src`, `npx vitest run`. Verify: all green, counts recorded here. Done 2026-10-11: control-plane `make code-quality` clean, `make test` 1620 passed, 9 skipped; frontend tsc and prettier clean, vitest 305 files, 3516 passed, 7 skipped.
- [x] 4.4 Owner check in the app. Verify: owner confirmation. Done: owner tested create, rename, duplicate and copy in the app on 2026-10-11, all passed.
- [ ] 4.5 Archive after merge. Verify: `openspec validate unique-agent-names-per-team --strict`.
