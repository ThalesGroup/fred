## Why

Teams can share prompts through the marketplace, but not agents: a team that wants another team's agent has to rebuild it by hand, or be an editor of both teams to use "Copy to…". Tracked in #3044. Copying an agent to another team already exists (`copy-agent-across-teams`), so the marketplace mostly adds who may publish, what is shown, and how users know whether the published version is current.

## What Changes

- **Editors publish.** No dedicated role: every team editor may publish while the platform admin has enabled publication for the team (owner decision, 2026-10-12, replacing a `team_publisher` role).
- **Publish from the agent card.** "Publish" and "Republish" are in the card's more menu, for editors only (hidden for everyone else and in personal spaces). Greyed with a tooltip when temporarily impossible: quota reached, private team, agent built on an administrator-only agent type. Every publication opens the same warning dialog: the whole configuration becomes visible to the organization, "I understand" checkbox, quota usage ("3 of 5 published"), Help Center link.
- **Snapshot.** Publishing stores what a copy to another team would carry: team-bound settings reset, configuration files captured. The marketplace shows and imports the snapshot only.
- **No edit lock.** Editors keep editing published agents. A save that changes a published agent puts it in the "Modified, not republished" state. A failed republication keeps the previous snapshot and shows the error. After an editor saves a published agent, a dialog that does not close on a scrim click offers "Publish" or "Ignore".
- **Removal.** Editors, the team admin and the platform admin can remove an entry. The entry is removed automatically when the agent is deactivated, suspended or deleted, when publication is disabled for the team, and when the team becomes private. A platform admin may add a reason. After an automatic or platform admin removal, the card shows a Removed state whose popover gives the reason, date and message; editors and the team admin can hide it, or an editor publishes again (counted against the quota). Deactivating or deleting a published agent goes through the critical confirmation dialog.
- **Card bottom bar.** One shared bar component: on the team card it shows the marketplace state (Published with likes and imports, Modified, Removed); members who are not editors see only Published. On the marketplace card it holds Like and Import.
- **Marketplace page.** An "Agents" marketplace page with search, team filter (from a card's team name), newest first by first publication, and empty states. Each card shows total likes (self-like allowed), imports and the last update date. Likes are tied to the published version ("N likes, including M since the update"); likes and imports are stored as dated rows, kept across removal and republication, so later trends can be computed (trends UI out of scope). A read-only "ID card" detail; no chat, edit or download.
- **Import.** Into the user's spaces where they can update agents, except the publishing team, reusing the agent copy: the dialog lists, per team, what the agent will lose, says the copy will be independent, and the result says what to reconfigure. The name is kept when free, otherwise `<name> (copie 1)`, `(copie 2)`… for a French user and `<name> (copy 1)`… for an English one; "Copy to…" and the Duplicate prefill switch to the same format; platform imports keep `<name> (2)`.
- **Admin "Marketplaces" section.** Same Default mechanism as the Features menu: a default "publication enabled" switch (off) and agents quota (5) that every team follows, existing and future, with per-team overrides and "back to Default". Turning a team's effective switch off removes its published agents. The prompt marketplace adopts this model in #3045.

## Capabilities

### New Capabilities

- `agent-marketplace`: publishing a team agent as a snapshot, its card bottom bar states (published, modified, removed), removal, the marketplace page with likes and import counts, the read-only detail, import, and the per-team agents marketplace settings.

### Modified Capabilities

- `agent-copy`: conflict names become `<name> (<word> <n>)`, word per UI language (from `copy-agent-across-teams`, to archive first).
- `agent-names`: same format for copies and imports (from `unique-agent-names-per-team`, to archive first).

## Impact

- **Capability runtime (fred-sdk, fred-runtime):** a pod operation that exports a capability's config for the marketplace (scope-private settings reset, files returned), and an optional inline-files field on `copy-config`. Additive; `RUNTIME-EXECUTION-CONTRACT.md` §8 entry, runtime OpenAPI regenerated.
- **ReBAC (`schema.fga`):** `can_publish_marketplace_agents` (team editors), `can_unpublish_marketplace_agents` (team editors and team admin); no new role.
- **Control plane:** two linear Alembic revisions (`platform_marketplace_settings` and two nullable `teammetadata` override columns; marketplace entry, file, like and import tables); publish, remove (optional admin reason), hide Removed state, like, marketplace list/detail, import-targets, import and admin settings endpoints; removal on deactivation, suspension, switch off and team made private; published count in the capability revoke preview; audit events; `authz-endpoint-matrix.yaml`.
- **Frontend:** regenerated `controlPlaneOpenApi.ts`; shared card bottom bar and `AgentCard` more-menu actions; publish, republish-proposal and critical dialogs; `MarketplaceAgents` page and detail; import dialog; admin page; fr and en strings.
- **Docs:** `CONTROL-PLANE-PRODUCT-CONTRACT.md`, `RUNTIME-EXECUTION-CONTRACT.md` §8, `REBAC.md`, `COMPONENT-UX.md`, Help Center fr and en.
- **Migration note:** one per PR, impact **minor**: the switch is off by default, so nothing changes until an admin turns it on.
