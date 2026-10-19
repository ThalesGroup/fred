## Why

A team's description states its objectives regarding its use of AI. It is a governance element: platform admins and people browsing the marketplace need to know what each team uses Fred for. Today it is optional (a nullable `String(180)` column, absent from team creation), so most teams have none, and the marketplace hides it on "Your teams" cards. Tracked in #3067.

## What Changes

- **Creation.** `POST /teams` (`CreateTeamRequest`, gated on `can_create_team`) requires a `description`, stored trimmed, 20 to 500 characters. The admin create-team form gets a required description field with a counter and a helper text on the team's AI objectives.
- **Edit.** `PATCH /teams/{id}` (`UpdateTeamRequest.description`, team_admin) still edits it, but an explicit `null`, a blank value or fewer than 20 trimmed characters is refused (422); the maximum becomes 500. The team settings field validates on blur and does not send an invalid value.
- **Database.** `teammetadata.description` becomes `NOT NULL`, `VARCHAR(500)`, with a CHECK on the trimmed length (at least 20). One Alembic revision on the control-plane head backfills missing, blank or too-short descriptions with a placeholder first.
- **Placeholder.** One constant, « Description à compléter par l'administrateur de l'équipe. », used by the migration, the platform import and the Knowledge Flow storage backfill. The `Team` DTO gains `description_is_placeholder`; team admins see a reminder on the team's home (agents page) and in team settings while it is in place.
- **Import.** A platform import never fails for a missing or short description: raw `teammetadata` rows and teams provisioned from `users.json` get the placeholder.
- **Personal spaces** keep no description (they have no `teammetadata` row).
- **Marketplace.** Every team card shows the description (3-line clamp), "Your teams" included. `TeamCard`'s `withDescription` prop is removed.
- **BREAKING (API):** `CreateTeamRequest.description` is required; `UpdateTeamRequest.description` can no longer clear the value. Only Fred's own frontend and importer call these routes.

## Capabilities

### New Capabilities
- `team-description`: a team's required description - its bounds and trimming at creation and edit, the database guarantee, the placeholder used by the migration and imports, the reminder to team admins, the personal-space exemption, and its display on marketplace team cards.

### Modified Capabilities
None. `team-member-roles` and `team-resource-spaces` do not cover team metadata.

## Impact

- fred-core: `TeamMetadataRow.description` (`team_metatada_models.py`), `TeamMetadataPatch`, `TeamMetadata`, `TeamMetadataStore.create` (gains `description`), shared constants (placeholder, 20, 500).
- Control plane:
  - an Alembic revision on head `93427a5fe874` (backfill, then `NOT NULL`, `VARCHAR(500)`, CHECK);
  - `teams/schemas.py` (`CreateTeamRequest`, `UpdateTeamRequest`, `Team.description_is_placeholder`), `teams/service.py` (`create_team`, `Team` mapping);
  - `import_export/importer.py` (raw `teammetadata` phase, `users.json` provisioning);
  - tests that create teams without a description.
- Knowledge Flow: `alembic/backfill/backfill_storage_usage.py` inserts the placeholder.
- Frontend: `AdminTeamsPage`, `TeamSettingsParameters`, `TeamAgentsPage` (reminder), `TeamCard`, `MarketplaceTeams`, fr/en translations, regenerated `controlPlaneOpenApi.ts`.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` (dated section), Help Center fr/en `teams-and-permissions.md`, `COMPONENT-UX.md` (TeamCard, AdminTeamsPage), migration note with impact `minor`.
