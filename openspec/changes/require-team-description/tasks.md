## 0. Preconditions

- [ ] 0.1 GitHub issue #3067 linked in proposal.md; branch `feat/team-description-required` from swift. Verify: `gh issue view 3067` and `git branch --show-current`.

## 1. Model and migration

- [ ] 1.1 fred-core `metadata_store.py`: add `TEAM_DESCRIPTION_MIN_LENGTH`, `TEAM_DESCRIPTION_MAX_LENGTH`, `TEAM_DESCRIPTION_PLACEHOLDER`, the `TeamDescription` type and `team_description_or_placeholder`; `TeamMetadataPatch.description` uses `TeamDescription` and refuses an explicit `null`. Verify: fred-core unit tests for the helper (missing, blank, 19/20 characters, 501 cut to 500, whitespace stripped) and for the patch (null, blank, short refused; unset ignored).
- [ ] 1.2 `TeamMetadataRow.description`: `String(500)`, `nullable=False`, and `CheckConstraint("length(trim(description)) >= 20", name="ck_teammetadata_description_min_length")` in `__table_args__`. `TeamMetadataStore.create(team_id, name, description)` with a required `description`. Verify: store test that a direct insert without a description, or with "Short", raises `IntegrityError` on SQLite.
- [ ] 1.3 Alembic revision in `apps/control-plane-backend/alembic/versions`, `down_revision = "93427a5fe874"`: normalise every description with `team_description_or_placeholder`, then batch-alter to `VARCHAR(500) NOT NULL` and add the CHECK; downgrade nulls placeholder rows, cuts to 180 characters, drops the CHECK and restores nullable `String(180)`. Verify: migration test seeding NULL, blank, "Ops", a padded valid description and a 300-character one through upgrade and downgrade; `make db-check-heads` (one head), `make db-check-sqlite`, and `make db-check-postgres-full` in `apps/control-plane-backend`; `alembic upgrade head` on the local database.
- [ ] 1.4 Adapt fred-core tests that create teams (`tests/security/test_platform_access.py`, `tests/teams/test_storage_usage_clamp.py`, `tests/teams/test_metadata_defaults.py`) to pass `TEAM_DESCRIPTION_PLACEHOLDER`. Verify: `make code-quality` and `make test` in `libs/fred-core`.

## 2. Control-plane API

- [ ] 2.1 `teams/schemas.py`: `CreateTeamRequest.description: TeamDescription` (required); `UpdateTeamRequest.description: TeamDescription | None` with a validator refusing explicit `null`; `Team.description_is_placeholder: bool = False`. Verify: schema tests for create (missing, short, 20, 500, 501, trimmed) and update (null, blank, short refused; unset accepted).
- [ ] 2.2 `teams/service.py`: `create_team` passes `request.description` to `store.create`; the `Team` mapping sets `description_is_placeholder`. Verify: API tests: `POST /teams` without description is 422 and creates nothing, with a valid one stores it trimmed; `PATCH` clearing or shortening is 422 and keeps the old value; a placeholder team reports `true`, a personal space reports `false` and no description.
- [ ] 2.3 Adapt control-plane tests that create teams (`test_get_team_by_id_projection_budget`, `test_team_registry_governance`, `test_import_export_team_metadata`, `test_import_export_users`, `test_metadata_stores`, `test_platform_access`, `test_platform_link_cleanup`) and `validation/scenarios/test_team_registry_authz.py`. Verify: `make test` in `apps/control-plane-backend`; the scenario file passes in its suite.
- [ ] 2.4 Regenerate the control-plane client: `cd apps/frontend && make update-control-plane-api`. Verify: `controlPlaneOpenApi.ts` shows `description` required on `CreateTeamRequest`, the bounds, and `description_is_placeholder` on `Team`; no hand edit.

## 3. Import and backfill

- [ ] 3.1 Importer raw `teammetadata` phase uses `team_description_or_placeholder(row.get("description"))`; `users.json` provisioning passes `TEAM_DESCRIPTION_PLACEHOLDER` to `CreateTeamRequest`; one report warning with the count of teams given the placeholder, worded « N équipes ont reçu une description par défaut. » / "N teams received a default description.". Verify: importer tests: a row without description, with "Ops", with a valid one, and a `users.json` team created on the fly; the import succeeds and the warning appears only when a placeholder was used.
- [ ] 3.2 Knowledge Flow `alembic/backfill/backfill_storage_usage.py` inserts `description=TEAM_DESCRIPTION_PLACEHOLDER`. Verify: `make code-quality` and `make test` in `apps/knowledge-flow-backend`.

## 4. Frontend

- [ ] 4.1 Shared constants `TEAM_DESCRIPTION_MIN_LENGTH` / `TEAM_DESCRIPTION_MAX_LENGTH` (with `MAX_TEAM_NAME_LENGTH` moved beside them) in one module imported by both forms. Verify: `npx tsc --noEmit`.
- [ ] 4.2 `AdminTeamsPage`: required description `TextArea` (500 counter, fr/en helper on the team's AI objectives, error after leaving the field under 20 trimmed characters); submit disabled until valid; request sends the trimmed description. Verify: vitest: submit disabled with a short description, enabled with a valid one, the mutation receives the trimmed value.
- [ ] 4.3 `TeamSettingsParameters`: `maxLength` 500; on blur an invalid trimmed value shows the field error and sends nothing, a valid one is sent trimmed; placeholder `ServiceNotice` for `canUpdateInfo`. Verify: vitest in `TeamSettingsParameters.test.tsx`: emptied field shows the error and calls no mutation; valid value calls it trimmed; notice shown for a team admin on a placeholder team, hidden otherwise.
- [ ] 4.4 `TeamAgentsPage`: the same reminder for `canUpdateInfo` when `description_is_placeholder`, pointing to team settings. Verify: vitest: shown to a team admin, hidden for a member and for a personal space.
- [ ] 4.5 `TeamCard`: delete the `withDescription` prop and always render the description; `MarketplaceTeams.renderCard` drops its boolean. Verify: `TeamCard.test.tsx` updated (description always rendered); marketplace vitest shows descriptions on "Your teams" cards.
- [ ] 4.5b Show a translated "to be completed" text when `description_is_placeholder` is true (TeamCard, team settings, any description display). Verify: vitest renders the en text for a placeholder team.
- [ ] 4.6 fr/en translation keys for the field label, helper, errors and reminder. Verify: the i18n key check used by the frontend tests passes; no missing key warning in vitest.

## 5. Docs

- [ ] 5.1 `CONTROL-PLANE-PRODUCT-CONTRACT.md`: dated section on the required description (create, update, bounds, placeholder, `description_is_placeholder`). Verify: the `Team`, `CreateTeamRequest` and `UpdateTeamRequest` tables in the contract match the generated OpenAPI.
- [ ] 5.2 Help Center fr/en `teams-and-permissions.md`: the description is required at creation, editable by team admins, and shown on marketplace cards; the reminder. Verify: both languages updated in the same commit.
- [ ] 5.3 `COMPONENT-UX.md`: `TeamCard` (no `withDescription`, description always shown) and `AdminTeamsPage` (description field). Verify: entries read consistently with the code.
- [ ] 5.4 Migration note `docs/swift/ops/migrations/3067-require-team-description.md`, impact `minor`, with a read-only query counting teams that will get the placeholder and the downgrade losses. Verify: the migration note check passes.

## 6. Verification and close-out

- [ ] 6.1 Quality gates: `make code-quality` from the repo root (warn first: it breaks a running Vite); `make test` in `libs/fred-core`, `apps/control-plane-backend`, `apps/knowledge-flow-backend`; frontend `npx tsc --noEmit`, `npx prettier --check src`, `npx vitest run`. Verify: all green, counts recorded here.
- [ ] 6.2 Owner check in the app: create a team (description required), edit and try to clear it, see the reminder on a placeholder team, see descriptions on every marketplace card. Verify: owner confirmation.
- [ ] 6.3 Record verification evidence here and archive after merge. Verify: `openspec validate require-team-description --strict`, then `openspec archive require-team-description`.
