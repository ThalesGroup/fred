---
schema: 1
title: "Prepare and coordinate the Fred v3.11.0 rollout"
impact: minor
configuration: none
configuration_reason: "No new settings originate in release preparation; this note consolidates the existing migration and configuration procedures in the release."
covers: [f951e343823efae25056c8e372d5f72e1c70974d]
---
## Applicability

Fred v3.11.0 preparation from code/v3.10.0. The covered dependency contribution
updates only Knowledge Flow's oauthlib lock entry from 4.0.0 to 4.0.1,
including artifact URLs and hashes; no configuration or application code changes.

## Prerequisites

Review the whole guide before starting. Record the previous runtime and
capability revision IDs and take coordinated database and object-store backups.
Plan a maintenance window: the in-thread message migration is incompatible with
old runtime replicas. Version 3.11.0 is the integrator's explicit selection;
it does not remove these operational constraints.

## Configuration

No additional configuration changes originate in this preparation.

## Upgrade

Apply this combined sequence, using the detailed procedures below for each
component. A procedure saying "deploy normally" describes only its own change;
it does not waive this release's coordinated maintenance window.

1. Before stopping old services, freeze PPT template edits, finish pending
   legacy analyses and ensure any successful platform replacement is promoted.
   Retain the legacy SQL rows and objects for backfill and rollback.
2. Block new user traffic, drain active turns and stop every old runtime
   replica. Warn users that unsent old queue or mailbox messages must be resent.
   Record migration revisions before applying the new ones.
3. Publish the new OpenFGA model before enabling analytics when schema sync is
   disabled; update any pinned model IDs. Adapt custom KPI, document-search
   and tabular clients as described below.
4. Apply the control-plane and runtime migrations with the new images. The
   control-plane adds preparation state and session activity; the runtime
   removes the old steering mailbox. Upgrade Knowledge Flow API/workers,
   agent serving pods, control-plane and frontend as one coordinated release
   before reopening traffic. Never restart an old runtime against the migrated
   runtime schema.
5. Keep PPT preparation flags disabled while validating the new worker and
   running the dry backfill and import. "Legacy reader" means the compatible
   reader in the new image, not restarting a pre-cutover runtime. Keep template
   edits frozen through reconciliation, then enable the new preparation flags
   and validate templates before allowing edits again.
6. Validate analytics permissions, document tools, cross-pod in-thread messages
   and PPT preparation. Reopen traffic only after those checks succeed.
   Azure model discovery, Zabbix monitoring, KPI history backfill and source
   re-ingestion are separate optional actions; none is required merely to
   reopen traffic.

Do not publish tags until the preparation PR is reviewed, merged and explicitly
approved. These instructions coordinate existing migrations; this preparation
does not add a new database revision.

## Validation

Validate migration coverage, the generated guide, package artifacts, stored
capability configuration compatibility and synchronized locks. Run root quality
checks and review PR CI before merge.

## Rollback

Reverting release metadata does not undo migrations in the release. Follow the
runtime cutover and PPT preparation rollback procedures and retain backups.

## Limitations

Package artifact validation is not a production migration rehearsal. Customer
overlays, real data backfills and multi-pod rollout checks require operator
validation. No tag or package publication is authorized by this PR.
