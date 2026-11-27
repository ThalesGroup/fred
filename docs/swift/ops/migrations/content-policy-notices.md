---
schema: 1
title: "Surface provider content decisions in managed chat"
impact: minor
configuration: local
configuration_reason: "The optional runtime YAML flag defaults to off and does not change packaged deployment defaults."
---

## Applicability

Applies to runtime pods that store conversation history. Content notices appear
as soon as the runtime and frontend are upgraded. Optional analysis defaults
to off.

## Upgrade

Apply Fred Runtime Alembic head `b131ce5af248` before starting upgraded runtime
pods. The revision extends `session_history` with three nullable fields and a
partial due index. Existing rows need no backfill. The analysis job is private
and shares the lifetime of the terminal history row.

## Prerequisites

Use the existing runtime database and ordinary migration process. PostgreSQL
provides shared worker leases when multiple replicas enable analysis.

## Configuration

Set `platform.content_policy_analysis: true` in the runtime configuration to
enable the optional worker on its replicas. It uses the platform default chat
binding selected for that turn, or the runtime default when the binding is
unset. The job uses the existing runtime database and model credentials.

## Validation

Replay a structured provider block and an ordinary validation error. Confirm
that the first produces an inline notice on the live turn and after reload.
Confirm the same exchange can still accept a new user message. When analysis
is enabled, check that a supported result augments that notice.

## Rollback

Disable analysis in runtime configuration to stop scheduling and processing
jobs. Basic notices continue. When rolling back the release, restore the
previous runtime and frontend before considering schema downgrade. Downgrade
removes private work fields while leaving existing terminal history metadata.

## Limitations

The runtime requires affirmative, structured evidence of a content decision.
A request-wide filter verdict may omit both the category and the origin.
Asynchronous provider filtering may expose provisional tokens until the
terminal signal arrives.
