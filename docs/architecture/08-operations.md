# 8. Operations

## Configuration, secrets and identity provisioning

## Deployment topology and environments

## Background work and scheduling

`fred-manager worker` runs the manager-owned Temporal lifecycle schedule on its
own queue. SQL receipts are the durable work source; acceptance has no Temporal
RPC. The worker polls due operations, applies bounded cleanup activities and
retains incomplete work for later sweeps. HTTP startup does not connect to Temporal.
[Manager operations](A3-manager-operations.md#space-deletion-lifecycle) defines
configuration, activation, progress and recovery.

## Logs, audit, metrics and diagnostics

## Migration, backup and recovery

On a dedicated local k3d, the factory's `make k3d-app-reset DIR=<fred checkout>`
previews a Fred data reset; `CONFIRM=reset` executes it. The product-owned
[reset hook](../../deploy/k3d/reset_data.py) retains Keycloak accounts, credentials,
installed images and infrastructure. It clears Fred data and authorization together,
including manager consent and bootstrap state, and removes pending Temporal work.
The same account therefore repeats CGU acceptance and platform bootstrap; importing
the bundle recreates spaces and grants while reusing existing Keycloak identities.

The hook refuses other applications and unsupported storage configurations. It
stops producers before deletion, replays installed SQL migrations and waits for
service readiness before reporting success. A partial failure leaves Fred stopped
and retains original replica counts for retry; it provides no data rollback.
This local reset is separate from production backup and recovery procedures.

## Implementation references

[Manager configuration, security audit and deployment](A3-manager-operations.md).
