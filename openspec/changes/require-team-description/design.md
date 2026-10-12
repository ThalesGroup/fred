## Context

See proposal.md for the why and specs/team-description/spec.md for the behaviour.

- The column lives in fred-core: `TeamMetadataRow.description` is `String(180)`, nullable (`libs/fred-core/fred_core/teams/team_metatada_models.py`). Its migrations live in the control-plane Alembic tree, current head `93427a5fe874`. Knowledge Flow writes the same table only from `alembic/backfill/backfill_storage_usage.py`.
- Rows are written by `TeamMetadataStore.create(team_id, name)` (called by `teams/service.py::create_team`), `TeamMetadataStore.upsert(TeamMetadataPatch)` (team PATCH), the importer's raw `teammetadata` phase (`TeamMetadataRow(...)` directly) and the Knowledge Flow backfill.
- `UpdateTeamRequest.name` already shows the pattern for "editable but never cleared": a validator that refuses an explicit `null` or blank value, skipped when the field is unset.
- Existing CHECK constraints in this tree are plain SQL strings (`ck_platform_ui_settings_singleton`), and column or constraint changes on `teammetadata` go through `op.batch_alter_table` for SQLite (`a8b9c0d1e2f3`).
- Frontend: `TextArea` already shows an `x / max` counter, an `explanation` and an `error`. `ServiceNotice` is the inline notice already used on `TeamAgentsPage`. `teamCapabilities` exposes `canUpdateInfo` (team_admin). The bare `/team/:teamId` route lands on `TeamAgentsPage`, the team's home.

## Goals / Non-Goals

**Goals:**
- One set of bounds (20, 500, trimmed) and one placeholder, defined once in fred-core and reused by every Python writer.
- The database is the final guarantee; API validation gives the readable 422 first.
- The smallest API change that lets the UI detect the placeholder.

**Non-Goals:**
- Descriptions for personal spaces.
- Translating the stored placeholder: the database keeps the French constant; only its display is translated (decision 6).
- Any change to team names, avatars or other team settings.

## Decisions

1. **Constants and a pydantic type in fred-core.** `fred_core/teams/metadata_store.py` gains `TEAM_DESCRIPTION_MIN_LENGTH = 20`, `TEAM_DESCRIPTION_MAX_LENGTH = 500`, `TEAM_DESCRIPTION_PLACEHOLDER`, a type `TeamDescription = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=500)]` and `team_description_or_placeholder(value: str | None) -> str` (strip; missing or under 20 gives the placeholder; over 500 is cut to 500 then stripped again). `StringConstraints` strips before checking lengths, so trimming and bounds are one declaration, and OpenAPI shows `minLength`/`maxLength`.
   - **Alternative:** a `field_validator` per schema. Rejected: three copies of the same rule (create, update, patch).
2. **Placeholder detection: `Team.description_is_placeholder: bool = False`.** Computed server-side in the `Team` mapping (`metadata.description == TEAM_DESCRIPTION_PLACEHOLDER`). One boolean on an existing DTO, inherited by `TeamWithPermissions`, and personal spaces get `False` by default.
   - **Alternative A:** the frontend compares `description` to a copy of the French string. Rejected: a hand-copied backend literal in TypeScript drifts silently, which the generated-client rule exists to prevent.
   - **Alternative B:** expose the constant through a settings endpoint. Rejected: a new field on another surface plus a second request, for the same answer.
   - **Alternative C:** keep the column nullable and treat `NULL` as "to complete". Rejected by the owner (`NOT NULL`).
3. **API validation.**
   - `CreateTeamRequest.description: TeamDescription` (required).
   - `UpdateTeamRequest.description: TeamDescription | None = None` with a validator refusing an explicit `null`, mirroring `_reject_blank_name`; blank strings fail `min_length` after stripping. Unset keeps today's partial-update semantics.
   - `TeamMetadataPatch.description` uses the same type and validator, so a non-HTTP caller of `upsert` gets the same rule.
   - The read models (`TeamMetadata.description`, `Team.description`) stay `str | None`: personal spaces have none, and no reader changes.
4. **`TeamMetadataStore.create(team_id, name, description)` takes a required `description`.** No default: every caller has to choose a real description or the placeholder explicitly. Tests that create teams pass `TEAM_DESCRIPTION_PLACEHOLDER` (already valid, 57 characters) rather than a new fixture helper.
5. **Database: `NOT NULL`, `VARCHAR(500)`, `ck_teammetadata_description_min_length` = `length(trim(description)) >= 20`.** `length` and `trim` exist in both SQLite and PostgreSQL. The constraint is also declared in `TeamMetadataRow.__table_args__`, so test databases built from the ORM metadata enforce it. SQL `trim` strips spaces only, whereas Python `strip()` strips all whitespace; every write path stores stripped values, so the CHECK is a backstop and the difference only matters for hand-written SQL.
6. **Migration, one revision on `93427a5fe874`.**
   - Upgrade: read `id, description` from `teammetadata`, normalise each in Python with `team_description_or_placeholder` (same rule as the app, no dialect differences in whitespace handling; teams are few), update the rows that change, then in `op.batch_alter_table("teammetadata")`: `alter_column("description", type_=String(500), existing_type=String(180), nullable=False)` and `create_check_constraint(...)`.
   - Downgrade: set placeholder rows back to `NULL`, cut descriptions over 180 characters to 180, then in batch mode drop the CHECK and restore `String(180)`, nullable. PostgreSQL refuses to narrow a `VARCHAR` holding longer values, so the cut must come first; it is lossy and the migration note says so.
   - The migration imports the placeholder from fred-core, as the owner asked for a single constant. Consequence: the constant is frozen. Changing its text later needs a data migration, otherwise rows backfilled with the old text stop being detected as placeholders.
7. **Import and backfill.**
   - Raw `teammetadata` phase: `description=team_description_or_placeholder(row.get("description"))`.
   - `users.json` provisioning: `CreateTeamRequest(..., description=TEAM_DESCRIPTION_PLACEHOLDER)`.
   - When at least one imported team gets the placeholder, the report carries one warning with their count, worded « N équipes ont reçu une description par défaut. » / "N teams received a default description." (owner wording), so the operator knows team admins have descriptions to write.
   - Knowledge Flow backfill: `TeamMetadataRow(..., description=TEAM_DESCRIPTION_PLACEHOLDER)`.
8. **Frontend.**
   - Bounds as two shared constants (`TEAM_DESCRIPTION_MIN_LENGTH`, `TEAM_DESCRIPTION_MAX_LENGTH`) in one module both forms import, beside where `MAX_TEAM_NAME_LENGTH` is moved to from `TeamSettingsParameters`.
   - `AdminTeamsPage`: a required `TextArea` (`maxLength` 500, counter, `explanation` on the team's AI objectives, error once the field has been left with fewer than 20 trimmed characters). `canSubmit` also requires a valid trimmed description; the request sends it trimmed.
   - `TeamSettingsParameters`: `maxLength` 500; on blur, an unchanged value does nothing, an invalid trimmed value sets the field error and sends nothing, a valid one is sent trimmed. A `ServiceNotice` above the field while `description_is_placeholder` and `canUpdateInfo`.
   - `TeamAgentsPage`: the same `ServiceNotice` for `canUpdateInfo` when the team reports a placeholder, pointing to team settings. Personal spaces never report one.
   - `TeamCard`: the `withDescription` prop is deleted and the description always renders (existing 3-line clamp); `MarketplaceTeams.renderCard` loses its boolean argument.
   - The client is regenerated (`make update-control-plane-api`); no hand-written type.

## Risks / Trade-offs

- [Every pre-existing team shows the French placeholder on marketplace cards until its admin writes one] → The reminder on the team home and settings; the import warning; the migration note gives a query counting affected teams.
- [The import warning counts teams but cannot tell an admin which] → Team admins see the reminder on their own team; the count is enough for the operator.
- [Downgrade loses descriptions beyond 180 characters] → Documented in the migration note; downgrades are exceptional.
- [The API change breaks an external caller of `POST /teams`] → Only the Fred frontend and importer call it; recorded in the contract and the migration note.
- [SQL `trim` and Python `strip` differ on non-space whitespace] → All writers strip in Python first; the CHECK only catches hand-written SQL.

## Migration Plan

Deploy normally: the control-plane database migration of the deployment applies the revision, backfilling before adding the constraints. The migration note (impact `minor`) gives a read-only query listing teams that will receive the placeholder. Rollback: `alembic downgrade` on the control plane restores the nullable `String(180)` column with the losses described in decision 6, together with the previous application version, which does not know the field.

## Display of the placeholder

6. When `description_is_placeholder` is true, the frontend shows a translated text (fr: « Description à compléter par l'administrateur de l'équipe. », en: "Description to be completed by the team administrator.") instead of the stored value, on team cards, team settings and anywhere the description is shown. Owner decision, 2026-10-12; frontend-only, no contract change beyond the flag.

## Open Questions

- None.
