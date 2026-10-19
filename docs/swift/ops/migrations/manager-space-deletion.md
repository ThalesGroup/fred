---
schema: 1
title: "Add deferred space deletion and the fred-manager Temporal worker"
impact: minor
configuration: production
configuration_reason: "The integrated Fred chart deploys manager API/worker with a shared policy catalog; lifecycle defaults off. Existing Python lifecycle behavior is unchanged."
---
## Applicability

Fred-manager installations on the Rust reconstruction branch. This adds platform-owner
space deletion; it does not replace Python content or conversation cleanup.

## Prerequisites

Back up manager SQL and its complete OpenFGA store together before upgrading.
Temporal must be reachable before activation. Keep the manager store separate from
Python's store. Stop old provisioning/operator writers during the upgrade.

## Configuration

`scheduler.lifecycle.enabled` defaults to false. The integrated Fred chart deploys
API and worker from one image and mounts `policies.purge_catalog_path` from their
shared catalog. Default retention is P7D, sweep PT10M, batch size 100. Worker queue
and workflow prefix start with `fred-manager-` and differ from ingestion's queue.
Connect/RPC timeouts are 5/10 seconds. The worker needs PostgreSQL/OpenFGA secrets,
not directory or root-bootstrap credentials. Settings are loaded at process startup.

## Upgrade

1. Keep lifecycle disabled in every process. Deploy the new API to apply migration
   0007 and publish the compatible additive OpenFGA model. Keep schema synchronization
   enabled for this initialization.
2. Finish replacing every API replica and operator/CLI producer. Deploy the separate
   `fred-manager worker`; it only loads the initialized schema and published model.
3. Verify worker registration and readiness. Only then enable lifecycle in the
   shared configuration and restart every affected API/worker process. An old
   producer still running is a reason to leave deletion disabled.

## Validation

On disposable data, configure a short retention and delete an empty project as a
platform owner. Verify 202, immediate retirement, stable receipt replay, no cleanup
before due time, and completed SQL/FGA cleanup after a sweep. Repeat with worker
interruption and verify recovery. `make test-lifecycle-temporal` automates this
journey on throwaway services; it does not touch deployed data.

## Rollback

Prefer a forward fix. Disable lifecycle in all processes before investigation.
Do not run an older binary against the newer schema/model, even after draining
requests: its pinned model contract is incompatible. A rollback requires stopping
all writers/workers, reconciling scheduled/in-flight Temporal work, and restoring
the coordinated pre-upgrade SQL/OpenFGA backup. Switching an image or editing a
model pointer alone is not rollback. Executed deletion has no undo API.

## Limitations

Only manager-owned folders, spaces and OpenFGA references are cleaned. A scope
containing document rows is refused. Accounts, consent and platform roles remain.
A retained receipt is an audit record for those two stores, not proof of cleanup
in content or conversation stores. Sweep cadence, backlog and outages delay execution.
