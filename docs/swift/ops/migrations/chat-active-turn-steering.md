---
schema: 1
title: "Queue and send messages during active agent turns"
impact: minor
configuration: none
configuration_reason: "Turn steering uses the existing shared runtime SQL engine and pool; no new service, connection setting or permission is required."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The runtime's shared PostgreSQL database must be available, as for checkpoints and history.

## Configuration

No configuration changes are required.

## Upgrade

Run the fred-runtime Alembic migration before updating runtime replicas. The normal chart migration job performs this step. The runtime checks for `runtime_turn_steering` at startup and remains unready if the table is missing.

## Validation

With two `fred-agents` replicas, start an agent turn on one pod, submit Send through the other, and verify the message reaches the agent at the next model boundary. Repeat with a tool confirmation and resume on the other pod.

## Rollback

Roll back the runtime and frontend together. The older runtime ignores the new table; downgrade the migration only after no updated replicas remain.

## Limitations

The ordinary pending list still lives in the browser and is lost on page reload. A pod failure between injection and the delivery event can leave the outcome uncertain; the UI does not retry automatically. Paused steering rows expire after 30 days.
