---
schema: 1
title: "Tracked ingestion relaunch with duplicate protection"
impact: minor
configuration: none
configuration_reason: "Ingestion admission adds a database index and a pending-submission table; existing scheduler and fast/medium/rich queue settings are unchanged."
---
## Applicability

Knowledge Flow deployments using document ingestion, including source synchronization.

## Prerequisites

Pause new uploads, source synchronization and processing requests. Let existing
Temporal ingestion workflows finish, including their queued and retrying children.
Allow task reconciliation to complete. Investigate remaining active tasks or
workflows; do not mark running work failed just to unblock the upgrade.

## Configuration

No configuration changes. Keep the common and fast/medium/rich workers configured
as before.

## Upgrade

After draining ingestion, stop the old Knowledge Flow API and workers, run the
normal Knowledge Flow Alembic migration, then start the new API and workers and
resume submissions. Avoid mixing old and new ingestion submitters during rollout.
The migration rejects duplicate active tasks for one document; resolve their real
workflow outcomes before retrying it.

No bulk re-ingestion is required. When a user relaunches an older document whose
profile was never recorded, the UI asks them to choose a profile.

## Validation

Relaunch a failed document. Check that one task appears in Resources/Activity,
survives a page reload and reaches a terminal state. A second concurrent request
must not start another ingestion. Confirm that rich/medium documents still use
their respective extraction workers.

## Rollback

Pause submissions again and drain both pending deliveries and running ingestions
before reverting Knowledge Flow. Do not drop the pending-submission table while
it contains accepted work. The added index/table may remain when rolling back
application code; an Alembic downgrade is only safe after the drain.

## Limitations

An unavailable worker or a Temporal retry is still active work, not permission to
relaunch. Historical tasks without a known workflow need investigation, not an
automatic timeout-based failure. The profile cannot be reconstructed for old
documents. Memory scheduling remains a single-process local-development mode.
