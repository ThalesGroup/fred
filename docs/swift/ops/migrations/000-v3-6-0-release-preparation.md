---
schema: 1
title: "Coordinated v3.6.0 upgrade and rollback"
impact: minor
configuration: none
configuration_reason: "Release preparation adds no setting; the minor impact comes from the existing Free-team admission, database and Knowledge Base publisher procedures."
---

## Applicability

Upgrade from Fred v3.5.0 to v3.6.0 with paired code and chart releases. This
sequence combines the procedures below and adds no migration of its own. Python
package publication remains a separate maintainer operation.

## Prerequisites

Back up the shared control-plane database and preserve the previous images,
chart and values. Rehearse the rollout and rollback with private overlays.

If platform filtering is enabled and any team uses Link access (Free), compare
that team's current members with its recorded Free-link joiners as described in
the team invite link note. Decide who needs an individual exception, an
authorized team, or a new Free enrollment before deploying new readers.

For each Knowledge Base pod, identify its publishing client and exact prefix.
Review existing published definitions and decide which publishers to register.
If participating backends use separate database roles, identify the roles that
need read access to the platform access link tables.

## Configuration

Register Knowledge Base publishers in the Fred chart values before deploying
the new control plane. The list stays empty on deployments without Knowledge
Base pods. Keep the existing `security.user_directory` selection. Release
preparation adds no other setting; `configuration_prod.yaml` is for local Docker
Compose, not the production reference.

## Upgrade

### Required coordinated rollout

1. Apply the Free-team admission decisions before the upgrade where continuous
   access is required. A person left to re-enroll through a Free link may be
   refused in the meantime.
2. Apply the control-plane Alembic head with the new migration image before
   starting updated backends. Revision `c3a7e5d9f1b2` adds `kind` and `paused`
   to existing links; the Fred chart's migration hooks are disabled by default,
   so run the deployment's migration job or equivalent command explicitly.
3. Grant each separate backend database role the read access specified in the
   team invite link note, after the new columns exist and before starting the
   updated services. Column grants avoid exposing reusable link tokens.
4. Deploy the matching Fred chart, updated control plane and frontend with the
   registered Knowledge Base publishers. The control plane must start before
   Knowledge Base pods replay publication. The frontend and control plane must
   both be updated before using the revised user-directory controls.
5. Deploy updated Knowledge Flow and agent runtime pods, then Knowledge Base
   pods. Validate admission and publication before resuming normal traffic.

### Optional activation and user data

- If platform filtering is still off, use the updated configured-directory
  lookup when reviewing the initial import and whitelist before activating it.
  A previously completed import stays completed; add missing identities through
  **Add users** instead of expecting another import.
- No document re-ingestion or search reindex is required. Previously orphaned
  data and partially failed unlinks are not repaired by this release.

## Validation

Confirm the control-plane migration head, startup of every participating
backend, and admission for affected Free-team members. Check that directory
search finds the intended identities, that team invitation links admit only
people who already have platform access, and that every registered Knowledge
Base pod publishes successfully. Check a current document search and a large
folder's inventory and deletion using the linked validation instructions.

## Rollback

Stop affected services before changing schema or images. Restore the previous
chart revision with its own values; if reusing current values with the older
chart, remove `knowledge_bases.publishers` first. An in-place downgrade of
`c3a7e5d9f1b2` deletes team invite links and restores the older, broader Free
admission rule. Use the database backup for a coordinated rollback when old
images have not been validated against the current schema and data. Recheck
platform admission before reopening traffic.

## Limitations

The chart does not enforce this deployment order. Private database grants,
overlays and Knowledge Base client identities require operator validation.
Stored Knowledge Base definitions are not revoked automatically. The paired
Fred tags do not publish Python packages.
