---
schema: 1
title: "Agents marketplace: publication settings, browsing, likes and imports"
impact: minor
configuration: none
configuration_reason: "Adds one control-plane migration, two team permissions and a pod endpoint; no configuration key or chart value changes."
---
## Applicability

Existing Fred deployments upgrading to this release, including third-party agent
pods built on fred-runtime. Publication is off by default, with a quota of five
agents per team. A platform administrator may enable it after deployment.

## Prerequisites

Back up the shared PostgreSQL database. The OpenFGA store must accept the new
model written by the control plane at startup.

## Configuration

No configuration changes are required. The publication default and per-team
overrides are stored in the database.

## Upgrade

1. Apply the control-plane Alembic head before starting the new Knowledge Flow
   pods. Revision `24c2f88374fe` (after `e9026d8e4db6`) adds the publication
   settings table, two nullable `teammetadata` columns and the four marketplace
   entry, file, like and import tables. Knowledge Flow reads `teammetadata`
   through the shared model and requires the new columns.
2. Deploy the control plane. At startup it writes the OpenFGA model with
   `can_publish_marketplace_agents` for team editors and
   `can_unpublish_marketplace_agents` for team editors and team admins. Existing
   tuples are unchanged.
3. Deploy the frontend and agent pods. Pods gain
   `POST /agents/capabilities/{id}/export-config`, and `copy-config` accepts
   `asset_files`. Upgrade the pods before enabling publication: an older pod
   cannot publish an agent with capabilities and may omit files on import.

Optional activation: in **Administration > Marketplaces**, enable publication
by default or for selected public teams and set their quotas. Editors of those
teams can then publish agents.

## Validation

- `alembic heads` shows `24c2f88374fe` as the single control-plane head.
- The admin Marketplaces page shows every team following Default (off, quota 5).
  A team admin cannot change these settings.
- With publication enabled, an editor can publish an agent. Another user can
  browse, like and import it into an eligible team, including its configuration
  files. Disabling publication removes the team's entries from the listing.
- A conflicting "Copy to..." name uses `<name> (copy 1)` or
  `<name> (copie 1)` according to the interface language. Platform imports
  keep `<name> (2)`.
- A disabled document's Delete menu item explains its state in a tooltip; the
  team members table uses small role chips.

## Rollback

Roll back the images, then run `alembic downgrade e9026d8e4db6` on the
control plane if the schema must go back. This drops marketplace settings,
entries, likes and import history. All marketplace data and overrides are lost.

## Limitations

Deleting a team now deletes its agents. Platform exports do not carry
marketplace settings or published agents. An agent whose type later disappears
from its pod stays listed until it is suspended; imports then fail.
