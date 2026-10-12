---
schema: 1
title: "Agents marketplace: team editors publish agents that every user can browse, like and import"
impact: minor
configuration: none
configuration_reason: "Adds a pod endpoint and control-plane tables; no configuration key, default or chart value changes."
after: [3044-marketplace-publication-settings]
---
## Applicability

Existing Fred deployments upgrading to this release, including third-party agent
pods built on fred-runtime. Nothing is published until a platform
administrator enables publication for teams: it is off by default
(publication settings: `3044-marketplace-publication-settings`).

## Prerequisites

A backup of the shared PostgreSQL database, as for any release carrying an
Alembic revision. The publication settings revision `b5e1c9d3a7f2` and its
OpenFGA model are applied first (`3044-marketplace-publication-settings`).

## Configuration

No configuration changes are required.

## Upgrade

1. Apply the control-plane Alembic head: revision `24c2f88374fe` (after
   `b5e1c9d3a7f2`) creates the empty `agent_marketplace_entry`,
   `agent_marketplace_entry_file`, `agent_marketplace_like` and
   `agent_marketplace_import` tables.
2. Deploy the control plane.
3. Deploy agent pods normally. They gain
   `POST /agents/capabilities/{id}/export-config`; `copy-config` accepts an
   optional `asset_files` field. Publishing an agent calls `export-config` on
   its pod and importing one sends `asset_files`: an older pod refuses the
   publication of an agent with capabilities and drops file-bearing
   capabilities at import, so upgrade agent pods before turning publishing on.

Optional activation: as a platform admin, enable publication by default or for
chosen teams and set the agents quota (`PUT
/control-plane/v1/admin/marketplace-settings/default` or
`PUT /control-plane/v1/admin/teams/{team_id}/marketplace-settings`; the
**Administration > Marketplaces** page ships with the marketplace UI). The
editors of those teams can then publish their agents.

## Validation

- `alembic heads` on the control plane shows `24c2f88374fe` as the single head.
- With publication enabled for a team, its editors can publish an agent
  (`POST …/agent-instances/{id}/publish`); disabling it again removes the
  team's published agents and leaves everyone's roles unchanged.
- "Copy to..." an agent with a configuration file (for example a ppt-filler
  template) into another team still succeeds and the copy keeps the file. When
  the destination already has an agent with that name, the copy is now named
  `<name> (copy 1)`, or `<name> (copie 1)` once the interface sends a French
  locale (previously `<name>_imported-1`); platform imports keep `<name> (2)`.
- `GET /control-plane/v1/marketplace/agents` answers `[]` until an editor
  publishes an agent; after a publication, another user can like it, read its
  details and import it into one of their teams, and the copy keeps its
  configuration files.

## Rollback

Roll back the images, then `alembic downgrade b5e1c9d3a7f2` on the control plane
if the schema must go back too: it drops the marketplace tables (published
agents, likes, imports), so every published agent, like and import record is
lost. The publication settings stay.

## Limitations

Deleting a team now also deletes its agents. Platform exports do not carry the
published agents. An agent whose agent type later
disappears from its pod stays listed until the agent is suspended; importing it
then fails for each destination.
