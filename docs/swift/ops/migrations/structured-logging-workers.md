---
schema: 1
title: "Use scoped diagnostic context in ingestion workers"
impact: minor
configuration: none
configuration_reason: "Workers now honor the existing app.log_format setting; reference values already select JSON and omitted local values remain text. No new configuration is required."
---
## Applicability

Knowledge Flow and Control Plane worker entrypoints, durable ingestion submissions and metadata/extraction/output activities, including spawned extraction children.

## Prerequisites

Deploy the preceding logging layers. Keep existing shared-storage, scheduler authorization and Temporal namespace/queue configuration. No database schema change is required.

## Configuration

Reference deployed worker configurations already select `app.log_format: json`; omitted local settings select text. Knowledge Flow worker/child generic logs remain stdout-only. Ensure the collector accepts role `worker`, bounded context fields and activity attempt metadata.

## Upgrade

Upgrade common and extraction workers before the API begins submitting new envelopes. New workers accept old queued payloads; old workers do not accept the new optional extraction arguments. Keep the worker cohort consistent before activating updated submission code. Workflow payloads only forward optional plain data; absent envelopes retain their original extraction activity arguments and replay behavior.

## Validation

Run one upload through durable delivery, metadata, extraction and output. Confirm correlation/person/team/document/task/workflow references; attempt must change on retry while operation identity remains. Inspect both worker and spawned child logs. Focused offline checks cover committed-outbox recovery, ambiguous delivery retries, legacy payloads, actual thread work and real spawned-child JSON/KPI output. No Temporal/GKE deployment canary was performed.

## Rollback

Stop updated submissions and drain jobs carrying envelopes before rolling workers back. Restore the earlier API submission code, then workers. Old payloads remain executable; logs lose inherited journey context. No data migration is needed.

## Limitations

This diagnostic envelope is not authorization and does not extend HTTP grants. Legacy jobs lack originating-request context; local activity references remain available. Temporal workflow logs retain their replay-aware logger and do not bind generic context inside replay. Collector severity/timestamp/field filtering and live multi-worker rollout must be validated during deployment.
