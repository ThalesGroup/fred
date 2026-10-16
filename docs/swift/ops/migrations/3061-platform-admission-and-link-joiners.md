---
schema: 1
title: "Retire the file whitelist and record Free-link joiners"
impact: minor
configuration: production
configuration_reason: "The chart removes global.whitelist, its ConfigMap and pod mount; deployments using that value must migrate admission restrictions to Platform access."
---

## Applicability

All Fred deployments receive the admission and Free-link changes. Deployments
that configured `global.whitelist` or mounted `users.txt` require configuration
changes before upgrading.

## Prerequisites

Back up the shared control-plane database. Review any existing file whitelist and
prepare equivalent rules or individual/team exceptions in Platform access. Check
the intended policy with the administrator preview and enable filtering before
removing the file whitelist, so admission remains restricted throughout rollout.

## Configuration

Remove `global.whitelist` from chart values; the new values schema rejects it.
Remove any separate `users.txt` mount. Platform access in the administrator UI is
the sole admission whitelist. Saved rules, exceptions and Free-link settings
remain available while its filtering switch is off.

## Upgrade

1. Apply the control-plane Alembic head before deploying the new control plane
   and readers. This contribution's revision, `9f6d3c2a1b08`, adds per-link
   join history without changing existing links or admission state. The release
   also includes later control-plane revisions; run the chain once to its head.
2. After equivalent Platform access filtering is enabled where needed, remove
   retired whitelist values and mounts. Stage the chart and services using the
   consolidated v3.5.0 sequence; the file no longer limits admission.

If a disposable preview database already applied an earlier draft of this
unmerged revision, recreate it from the current migrations before testing.
Alembic does not rerun an applied revision when its contents change. For a
preview database that must retain data, back it up and explicitly add the
snapshot and deletion columns, remove the joiner's user foreign key, and
backfill the snapshots from `users` before starting the new control plane.
Existing production databases have not applied this new revision.

The detailed admission deployment sequence remains in
[the platform-access migration note](2965-platform-access-planning.md).

## Validation

Confirm that disabling filtering admits an authenticated, active person and
that re-enabling it restores the saved restrictions. Confirm that a current
platform administrator stays admitted. Use a new Free link to join a team and
check that its administrator view shows the joiner's username and names.

## Rollback

Reverting to an older chart requires restoring any old whitelist values and
mount deliberately, after reviewing the resulting admission policy. Back up
the database before downgrading: dropping `9f6d3c2a1b08` removes recorded join
history. Disabling the SQL filtering switch is an explicit way to widen
admission without deleting its saved configuration.

## Limitations

Earlier link openings or joins cannot be backfilled into the new history.
Recorded joins survive team departure, account deletion and link expiry or
revocation. After account deletion, they retain the last recorded names and
username with a deleted marker. Only explicit link-history deletion removes
them. A successful OpenFGA grant
and the SQL join record are separate operations; a failed SQL commit after the
grant can require operator reconciliation.
