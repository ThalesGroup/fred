## Context

See proposal.md for the motivation. Current state, verified in the code:

- **Prompt marketplace.** A live `prompt.published` flag (revision `0dd1e72106af`), `product/service.py` `list_marketplace_prompts`, `import_published_prompt_into_team`; routes `/control-plane/v1/marketplace/prompts[...]`; frontend `pages/marketplace/MarketplacePrompts` (`SearchInput`, `FilterChips`), `MarketplaceNavbar`. Contract §39, `PROMPTS.md` §6.1.
- **Agent copy** (`product/agent_copy.py`, contract §58). `copy_agent_instance_to_team` calls the pod's `POST /agents/capabilities/{id}/copy-config` per usable capability (404/422 drop it) and names with `free_imported_name` (`agent_instances/names.py`, merged with #3043, unique index on `(team_id, lower(display_name))`). The pod (`fred_runtime/capabilities/copy.py`) resets scope-private fields across teams and reads `AssetKey` files from the **source** instance with the caller's token (needs `can_access_files` on the source team).
- **Suspension and lifecycle.** Every suspension goes through `agent_instances/suspension.py` `suspend_instance` → `store.set_suspension`, including `capabilities/enablement.py` `suspend_dependent_instances` (capability or template revoked). Deactivation is a `PATCH` of `status`; deletion is `unenroll_agent_instance`. `capabilities/impact.py` previews a revoke (`CapabilityImpactPreview`).
- **Teams.** `schema.fga` `type team` roles; `teams/service.py` grant/revoke and `_remove_all_team_member_relations`; `teammetadata` holds platform-admin per-team settings (storage limit, retention) and `visibility`, changed in `update_team`. Frontend `TeamRoleChips`, `TeamSettingsParameters` (visibility).
- **Features default mechanism.** A platform default (`set_capability_default_on`, an org-level `default_on` ReBAC marker) plus a per-team tri-state `disabled | default | enabled`; `reset_capability_for_team` (`capabilities/enablement.py`) clears the team's explicit position; UI: default toggle in `admin/FeaturesPage/FeaturesPage.tsx`, Disable / Default / Enable segmented control in `CapabilityTeamMatrixDrawer.tsx`. Platform singletons follow `platform_ui_settings` (one row, absent = never set).
- **Prompt popularity.** Scalar counters on the prompt row (`session_count`, `import_count`), sorted in the listing; Home `MarketplaceTopPrompts` sorts by `session_count` and draws its 7-day sparkline from a placeholder (`mockWeekSeries`) because no history exists.
- **Frontend.** `AgentCard` more menu (`edit | toggle | duplicate | copyTo | delete`); icon computed by `shared/utils/agentIcon.ts` (nothing to snapshot); `ConfirmationDialog` with `criticalAction` (Cancel filled primary, confirm text in error color); `CopyToTeamsDialog` with per-team readiness.

## Goals / Non-Goals

**Goals:**
- Import never touches the publishing team: everything it needs lives in the snapshot.
- Reuse the copy path end to end (template check, `copy-config`, dropped capabilities, naming).
- Removal happens where the state changes, so no caller can forget it.
- Likes and imports survive removal and republication, with enough history for later trends.

**Non-Goals:**
- Prompt marketplace (#3045), moderator role (#3046), template-disappearance sweep (#3047). A template that leaves a pod is handled by #3047's suspension, which removes the entry.
- Edit lock, icon picker, author person, file download.
- Trends UI (Home "Trends" tab, sparklines of likes and imports); v1 only stores the history it will read.

## Decisions

### 1. One entry row per agent, kept across removal

- `agent_marketplace_entry`: `entry_id` (PK), `agent_instance_id` (unique, FK `agent_instance` `ON DELETE CASCADE`), `team_id` (indexed), `state` (`published | removed | dismissed`), `removed_reason`, `removed_message` (optional platform admin text), `removed_at`, snapshot columns (`template_id`, `source_runtime_id`, `source_agent_id`, `display_name`, `description`, `tuning_json`, `capabilities_json` = id, name, description captured at publish), `version` (publication counter, +1 on every publication), `first_published_at` (listing order), `published_at` (current version), `snapshot_source_updated_at` (the agent's `updated_at` read when the snapshot was taken).
- `agent_marketplace_entry_file`: `(entry_id, asset_key)` PK, `filename`, `size`, `content` (`LargeBinary`), FK cascade.
- `agent_marketplace_like`: `like_id` PK, `entry_id` (FK cascade), `user_id`, `version`, `created_at`, `removed_at` (soft unlike); partial unique index on `(entry_id, user_id)` where `removed_at` is null. Re-liking inserts a new row.
- `agent_marketplace_import`: `import_id` PK, `entry_id` (FK cascade), `target_team_id`, `user_id` (importer), `agent_instance_id` (resulting agent, nullable, FK `SET NULL`, for a later "update available"), `version`, `created_at`; one row per successful destination. No denormalised `import_count`: volumes are small and the listing counts with one grouped query.
- **Why rows, not counters:** the prompt marketplace keeps only scalars, which is why its Home sparkline is a placeholder. Dated rows let a later trends slice compute per-day likes and imports (`created_at`, `removed_at`) and "most popular" over a period without a schema change; it would read these two tables only.
- **Removal** sets `state = removed` (or `dismissed`, see 4) and deletes the file rows; the row, its likes and imports stay. **Republication** replaces the snapshot columns and files and sets `state = published`. **Agent deletion** cascades everything; team deletion deletes its agents, hence its entries.
- **Why files in the database:** every removal is one transaction with no orphan blob; volume is bounded by the quota and pod asset limits. Alternative `ContentStore` rejected (compensating deletes, orphans).
- **No author column:** the team is the author, its name read live from `teammetadata`; the publishing user is in the audit event only.

### 2. Publish exports through the pod; import reuses `copy-config` with inline files

- New pod operation `POST /agents/capabilities/{id}/export-config` (publishing editor's token, source team/instance): upgrade, `reset_scope_private`, read `AssetKey` files; returns `{schema_version, config, files: {asset_key: base64}}`.
- `CapabilityConfigCopyRequest.asset_files` (optional): when set, `prepare_capability_copy` takes files from it instead of `AgentAssetPort`.
- Publication is all or nothing: any export failure fails it and names the capability or the cause. A failed **re**publication never touches the entry: the previous snapshot stays published, the error is returned (422 for a capability-level cause, 503 for an unreachable or failing pod), and the agent stays Modified. Typical causes: a capability no longer installed on the pod (404), a capability unable to prepare its configuration for a copy (422), a missing or unreadable configuration file (422).
- Older pods: no `export-config` → publication refused for that capability; no `asset_files` → capability dropped at import. Additive, §8 entry.

### 3. Import = `copy_agent_instance_to_team` on a snapshot source

The snapshot maps to the copy source shape (record view with `team_id` = publishing team, `agent_instance_id` = `entry_id`, plus `asset_files`). Naming is the copy rule (`free_imported_name`, see 11). The publishing team is excluded from destinations. Each successful destination inserts an import row. `import-targets` reuses the copy readiness (template enabled, missing capabilities with names) for the per-team loss list; the result returns dropped capabilities and copy notices, and the UI adds a fixed line about team-bound settings (libraries, documents).

### 4. Marketplace state on the team card, derived where possible

- **Published:** `state = published` and `agent.updated_at == snapshot_source_updated_at`.
- **Modified, not republished:** `state = published` and `agent.updated_at != snapshot_source_updated_at`. Reading `updated_at` before the export means a save during a publish still shows as Modified. `update_agent_instance` must not bump `updated_at` when nothing changed; publish, like and hide never touch the agent row.
- **Removed:** `state = removed`, set only by automatic causes (`deactivated | suspended | switch_off | team_private`) and platform admin removals (`removed_by_platform_admin`, optional `removed_message`). A removal by an editor or the team admin sets `dismissed` directly. "Hide" sets `dismissed` for the team.
- **Visibility:** the summary exposes Modified and Removed only to editors and the team admin; other members get Published or nothing.
- `ManagedAgentInstanceSummary.marketplace: {state, published_at, modified, removed_reason, removed_message, removed_at, like_count, import_count, version} | null`.

### 5. Removal where the state changes

`AgentInstanceStore.set_suspension` and the status update to disabled mark the entry `removed` in the same session; deletion cascades. `update_team` to private and the effective switch-off path remove the team's published entries in the same request. The store returns what it removed so the caller emits `agent.unpublished` with the reason (`agent.published` on publish). Reactivation never republishes; the frontend opens the republish proposal for editors.

### 6. Authorization

- `schema.fga` `type team`: `can_publish_marketplace_agents: team_editor`; `can_unpublish_marketplace_agents: team_editor or team_admin`. No dedicated role (see "Owner decision: editors publish" below). `team_admin` and `team_editor` are orthogonal (REBAC.md), so a team admin who is not an editor removes and hides entries but does not publish.
- Publish check: ReBAC, switch on, team public, template public, not personal, and for a new publication (including one after a removal) `published count < quota`. Republishing a published entry ignores the quota; cleaning up teams above a lowered quota is left to a future moderator (#3046).
- Removal: one `can_remove_from_marketplace(user, team_id)` = team permission **or** `OrganizationPermission.CAN_MANAGE_PLATFORM`; #3046 adds the moderator there.
- Admin settings: `CAN_MANAGE_PLATFORM`. Likes: any authenticated user, own team included, published entries only. Hide: `can_unpublish_marketplace_agents` (editors and team admin).
- Concurrency: publish, republish and remove lock the entry row (`SELECT … FOR UPDATE`) and compare the caller's `expected_version` (sent from the card); a mismatch returns 409 and the frontend refetches the agent list.

### 7. Settings: platform default plus team overrides (Features pattern)

- **Semantics and UI** reuse the Features mechanism: a default every team follows, a per-team override, and "back to Default" (the `reset_capability_for_team` idea). The switch uses the same Off / Default / On segmented control as `CapabilityTeamMatrixDrawer`; the quota is a number field with a "Default (n)" reset.
- **Storage:** the Features default lives in ReBAC because it gates access; a quota is an integer, so it cannot. Default: singleton table `platform_marketplace_settings` (`agents_publishing_enabled` false, `agents_publish_quota` 5), same pattern as `platform_ui_settings` (absent row = built-in defaults). Overrides: two nullable `teammetadata` columns, `agents_publishing_enabled` and `agents_publish_quota` (null = Default, check `>= 1`), next to the storage limit and retention. Effective value = override if set, else default. Prompt columns come with #3045.
- **Effective switch on → off** (override, reset to Default, or default change): remove the team's published entries in the same request; the count is previewed per affected team and summed.

### 8. API

- `POST /teams/{team_id}/agent-instances/{id}/publish` (publish or republish), `POST …/unpublish` (`reason` accepted from a platform admin only), `POST …/marketplace-dismiss` (Hide); publish, republish and unpublish take `expected_version` (absent for a first publication).
- `GET /marketplace/agents` (published only, newest first by `first_published_at`, `q`, `team_id`; total likes, `liked_by_me`, import count, `published_at`, team name), `GET /marketplace/agents/{entry_id}` (files as name + size only, no content endpoint exists; likes total and since the current version), `PUT|DELETE /marketplace/agents/{entry_id}/like`, `GET …/import-targets`, `POST …/import` `{target_team_ids}`.
- `GET /admin/marketplace-settings` (default, and per team: override, effective values, published count), `PUT /admin/marketplace-settings/default`, `PUT /admin/teams/{team_id}/marketplace-settings` (null field = back to Default), `GET /admin/marketplace-settings/default/impact` and `GET /admin/teams/{team_id}/marketplace-settings/impact` preview a change (entries removed); write responses report the same count.
- `TeamWithPermissions.marketplace`: switch, quota, published count (publish greying, "3 of 5", visibility warning).
- `CapabilityImpactPreview.published_instances`.

### 9. UI

- **Shared bottom bar:** one component in the `AgentCard` bottom slot. On the team card it displays the state (none / Published + likes + imports / Modified in warning colour, counters kept / Removed opening a popover with reason, date, admin message and "Hide" for editors and team admin). On the marketplace card it holds the Like (pressed state from `liked_by_me`, `aria-pressed`) and Import actions with counters and "Updated on <date>".
- **AgentCard (team):** the more menu renders when the user can edit **or** remove from the marketplace (team admin who is not an editor), items filtered per permission (today only with `canManageAgents`). Editors: Publish / Republish (greyed for quota, private team, administrator-only agent type; "Publish" after a removal); Remove for editors and team admin. Deactivate/Delete of a published agent use `ConfirmationDialog` `criticalAction`.
- **Publish dialog:** warning (configuration visible to all; "Anyone who imports this agent receives a copy of its files (<names>)"), "I understand" checkbox, "3 of 5 published", the only Help Center link of the feature.
- **Republish proposal:** after an editor's save of a published agent, or an editor's reactivation of an agent removed by deactivation; `Dialog` that ignores scrim clicks, "Publish" (opens the publish dialog, greyed with the quota reason when reached) / "Ignore".
- **Team pages:** visibility change to private shows the removal count.
- **Marketplace page:** `MarketplaceAgents` with `SearchInput` and a searchable team select, newest first (first publication), empty states; marketplace variant of `AgentCard` (no chat, enable toggle or more menu). Detail: read-only "ID card" with "N likes, including M since the update of <date>". Import: `CopyToTeamsDialog` without the publishing team, per-team losses, the independence sentence, then a result step.
- **Admin "Marketplaces":** a Default row (switch, quota) above the team table; per team Off / Default / On, quota with reset to Default, published count; every on → off confirmation states the removal count, none when it is zero.
- **Wording:** never "template" for users ("agent type"). i18next plural keys for likes, quota usage and removal counts; dates through the locale formatter.

### 11. Copy names: `<name> (<word> <n>)`

On a name conflict, marketplace imports and "Copy to…" name the copy `<name> (copie 1)`, `(copie 2)`… for a French user and `<name> (copy 1)`, `(copy 2)`… for an English one (`free_imported_name` changes from `_imported-<n>`); a free name is kept, numbering starts at 1 and the first free number wins. Owner decision: the word reads naturally to the person who made the copy, which outweighs the name being stored for a team whose members may use the other language. The frontend sends its UI language as an optional `locale` (`fr` | `en`) on the copy and import bodies (no existing pattern carries the UI language to the control plane); the word comes from a fixed server map, never from client text, English when absent. A platform import restores rather than copies, so it keeps `<name> (2)` (`free_numbered_name`, owner decision), like the upgrade rename of `unique-agent-names-per-team`. The Duplicate dialog prefills the same `<name> (copie 1)` form in the UI language (`freeAgentName`, word from i18n), the user can still edit it. This change carries MODIFIED deltas for `agent-copy` and `agent-names`; those two in-flight changes must be archived first so their specs exist. Prompts alignment (#3045) should follow the same format.

### 10. Delivery in four stacked PRs

1. Runtime: `export-config`, `asset_files`, §8 entry.
2. Settings and role: `teammetadata` columns (revision 1), default and override storage (`platform_marketplace_settings`), admin endpoints and page.
3. Marketplace backend: tables (revision 2), publish, removal paths, likes, listing, detail, import, impact count, audit, copy-name format.
4. Marketplace frontend and Help Center: shared bottom bar, card menu, dialogs, marketplace page and detail, import dialog, visibility warning, docs.

## Risks / Trade-offs

- [Large configuration files in base64 JSON and Postgres] → bounded by pod asset limits and the quota; files deleted on removal.
- [`updated_at` bumped by a non-user write (suspension, status)] → those writes remove the entry anyway; tests pin that publish, like and hide never touch the agent row.
- [Every editor can publish what the whole organization sees] → per-team switch off by default, the quota, the warning dialog, and removal by the team admin and the platform admin.
- [Template leaves a pod] → entry stays listed until #3047 suspends the agent; import then fails per destination with the template-not-enabled refusal.

## Migration Plan

- Two Alembic revisions (PR 2, PR 3), each parented on the `swift` head when it lands; `alembic heads` shows one head.
- `schema.fga` gains two computed permissions; existing tuples untouched. Switch off by default: no visible change until an admin turns it on.
- Rollback: image rollback plus `alembic downgrade` (drops entries, likes, imports and the settings).
- Migration note per PR, impact minor.

## Implementation notes

PR 2 (settings):

- **Published counts before the entries exist.** `marketplace_settings/effective.py` `count_published_agents` returns 0 per team and `marketplace_settings/service.py` `_remove_published_agents` removes nothing; PR 3 plugs the entries store into these two seams (counts on the admin page and `TeamWithPermissions.marketplace`, removal on switch off, impact counts).
- **Back to Default** is `PUT /admin/teams/{team_id}/marketplace-settings` with null fields, as in §8; there is no separate reset route. The impact endpoints take the proposed switch as the `agents_publishing_enabled` query parameter (omitted = Default for a team); the quota never changes the impact.
- **Frontend checks** ran through `npx tsc`, `prettier`, `eslint` and the touched `vitest` suites instead of `make test` in the frontend, which wipes the running Vite cache.

PR 3 (marketplace backend):

- **File key.** `agent_marketplace_entry_file` is keyed by `(entry_id, capability_id, asset_key)`, not `(entry_id, asset_key)`: asset keys are chosen per capability (ppt-filler uses a fixed key), so two capabilities of one agent could collide, and import hands each capability its own `asset_files`. `filename` is the asset key's last path segment; the pod's export carries no other name.
- **Version moves on removal too.** `version` grows on every publication and every removal (manual or automatic), so a republication and a removal sent from the same card version cannot both apply (the second gets 409). Likes record the version they were given on; "since the update" counts likes on the current version, which is always a publication's.
- **Quota race.** Publication writes take a per-team Postgres advisory lock in the same transaction as the entry's `SELECT … FOR UPDATE`, so two new publications of one team cannot both pass the quota and two first publications of one agent cannot both insert (the unique index would also refuse the loser, mapped to 409).
- **`updated_at` precision.** `AgentInstanceStore.update` writes only the columns that actually change and stamps `updated_at` (and `updated_by`) only then, to the microsecond: the former second precision let a save made in the same second as the publication read as unchanged.
- **Card state for dismissed entries.** Editors and the team admin get `marketplace.state = dismissed` with its `version` (the frontend treats it as no bar, and needs the version to publish again); other members get only `published` entries, never `modified`.
- **Refusal statuses.** Personal space and missing ReBAC permission answer 403; private team, switch off, non-public agent type, quota and stale version answer 409, each with a stable `detail.code` (`marketplace_*`). A failed export answers 422 or 503 with `capability_id` when known.
- **Import audit.** Each destination still emits `agent.copied` from the agent copy, with the entry id as source agent; the import row is the marketplace record.
- **Team deletion** did not delete the team's agents; it now does (`AgentInstanceStore.delete_by_team`), so their entries, likes and imports cascade. Like a single deletion, it first copies each agent's name onto its sessions (`agent_display_name`), under a row lock on the team's agents. It then emits one `agent.deleted_total` per agent (same dims as a single deletion, through the KPI writer) and one `agent.unpublished` audit with reason `team_deleted` per entry that was published, captured in the same transaction before the cascade. `team_deleted` is audit-only: no card ever shows it, so it has no translation.
- **Single agent deletion** of a published agent takes the entry down inside the deletion's transaction and audits `agent.unpublished` with reason `deleted` (actor: the deleting user) once committed; before, the entry cascaded silently.
- **Graph agents saved with `[]`.** Publication and Copy to… take a template without free selection's included defaults usable by the team (`template_default_capability_ids`, shared with the save path) instead of the stored selection, which older saves left empty while the runtime runs the defaults; stored configs are kept.
- **`alembic check`** on the dev database reports one pre-existing drift unrelated to this change (the `prompt.command` column comment).
- **Switch-off versus publication.** The switch-off removes entries after saving the setting, in a separate step, so a publication whose pre-checks ran before the save could land after the removal. `save_publication` now re-reads the effective switch, the quota and the team's visibility under `FOR SHARE` locks, `platform_marketplace_settings` row first, then the `teammetadata` row, and refuses with `marketplace_switch_off` / `marketplace_team_private`. The Default write locks its row `FOR UPDATE`; the override and visibility writes lock the team row by their `UPDATE`. Either the write waits for the publication and then removes it, or it commits first and the publication sees it. Postgres only: SQLite ignores the locks, so the tests prove only the re-read (setting flipped during the export).
- **Deactivation and suspension versus a first publication.** Nothing removes an entry that does not exist yet, so `save_publication` also share-locks the agent row (after the team locks, before the entry row, the order deactivation and suspension take: agent row, then entry) and refuses a disabled, suspended or deleted agent with `marketplace_agent_inactive`. Postgres only, like the switch-off re-read.
- **Secret values stay out of the snapshot.** Publication drops every tuning value whose field is typed `secret` in the agent's stored fields or its template's (union, as `displayable_configuration` does for Knowledge Base instances), so the detail never shows it and an imported copy has it unset.

PR 4 (marketplace frontend, team side):

- **Files sentence.** The team side cannot know file names before a publication (the export runs at publish time), so the publish dialog names the selected capabilities that declare file slots: "…a copy of its files (PowerPoint filler)".
- **Administrator-only agent type** is detected by the agent's template missing from the team's agent types list (which never includes non-public ones); while that list is unknown or failed, Publish is not greyed and the backend refusal (`marketplace_template_not_public`) is shown.
- **Republish proposal** uses `ConfirmationDialog` with two new optional props, `dismissible={false}` (scrim and Escape inert) and `confirmDisabled`, rather than `Dialog`: `DialogPrimitive` is part of the published `@fred-oss/ui` surface and stays unchanged. It opens after a save only when the refreshed agent reads as modified, so a no-op save proposes nothing.
- **Help Center link** of the publish dialog points to the Agents page (`/help/<lang>/features/agents`); the Help Center slice adds the marketplace section there.
- **Removal counts.** The platform default-off confirmation on the Features page shows `published_instances`; the per-team revoke in `CapabilityTeamMatrixDrawer` has no confirmation today and is left as is. Going private shows a critical confirmation with `TeamWithPermissions.marketplace.published_count`.
- **Remove** from the card asks a plain (non-critical) confirmation; a platform admin's removal with a reason has no team-card entry point (left to the marketplace detail).

PR 4 (marketplace frontend, marketplace side and Help Center):

- **Removal from the detail.** `MarketplaceAgentDetail` gains `agent_instance_id` so a platform admin's removal (optional reason) reuses the team-scoped `POST …/unpublish` with the entry's `version`; no marketplace-side removal route is added.
- **Client-side filtering.** The page loads the whole listing and applies the search and team filter itself (the endpoint's `q` and `team_id` stay unused): the page can tell "nothing published" from "nothing matches". Owner decision: no team select; the search also matches team names (case- and accent-insensitive), and clicking a card's team name sets the team filter, shown as a removable `Chip` in a chips row under the header (future category chips go there).
- **Shared components extended.** `PageEmptyState` gains an optional `description` line (an additive prop of a component in the published `@fred-oss/ui` surface) for the explanatory empty states; `CopyToTeamsDialog` gains `excludedTeamIds`, which drops the publishing team from the list instead of showing it as the origin.
- **Import errors.** Per-destination results carry a stable code only for `marketplace_publishing_team` and `agent_name_conflict`; those are localized, every other failure shows a generic localized line rather than the backend's English text.
- **Help Center link** of the publish dialog now targets the marketplace heading of the Agents page by anchor (`#the-agents-marketplace`, `#la-marketplace-des-agents`); a content test checks that every in-corpus anchor link resolves. The copy-name example there now reads `Analyst (copy 1)` / `Analyste (copie 1)`.
- **Bar always present while the team can publish** (owner feedback after review): a not published or hidden agent shows "Not published", with Publish in the more menu for editors, instead of no bar; when the team cannot publish, no card shows the bar, so the grid stays even. A Removed state is therefore not shown once the switch is off or the team is private. The bar is pinned under the actions row on `surface-container-high` (one step above the card's `surface-container`), on both cards.

### Owner decision: editors publish (2026-10-12)

After team review the product owner dropped the dedicated `team_publisher` role. Every team editor publishes and republishes; editors and the team admin remove and hide; the platform admin's removal with a message is unchanged. The admin switch keeps its Default + override mechanism and storage but now means "publication enabled" for the team's editors (columns `agents_publishing_enabled`, renamed in the not yet deployed revision `24c2f88374fe`); turning it off removes the team's published agents and its confirmation states only that count. Gone with the role: grant/revoke rules, the Publisher chip, the publisher count and "no publisher" flag, the last-publisher warning and banner, and the `team-member-roles` delta. `team_admin` stays orthogonal to `team_editor`: a team admin who is not an editor removes but does not publish.

Deferred: prompt marketplace alignment (#3045) no longer needs a publisher role shared between agents and prompts; it can reuse the editor rule and the same settings mechanism.
