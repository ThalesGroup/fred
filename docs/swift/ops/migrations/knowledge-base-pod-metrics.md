---
schema: 1
title: "Knowledge Base pods expose operational metrics"
impact: none
configuration: none
configuration_reason: "Only a Knowledge Base pod's own configuration.yaml gains an optional observability block, in its own image and chart; Fred's applications, chart values and schemas are unchanged."
no_action_reason: "Fred deployments are unaffected. A Knowledge Base image exposes the new endpoints only once rebuilt against fred-sdk 4.4.2 and bound outward by its own deployment."
---
## Applicability

Knowledge Base images built on `fred-sdk[knowledge-base]` 4.4.2 or later. Fred's
own applications and chart are not affected. The `fred-sdk` patch release also
refreshes the local lockfiles of every project that depends on it by path.

## Prerequisites

No prerequisites for Fred. A Knowledge Base deployment that wants to be scraped
needs Prometheus, and the Prometheus Operator CRDs if it uses a ServiceMonitor.

## Configuration

A pod's `configuration.yaml` accepts an optional `observability` block, read with
the keys every Fred backend uses: `observability.kpi.prometheus` (`fred_kb_*`
series, port 9000) and `observability.temporal.prometheus` (`temporal_*` series
from the workflow engine, port 9001). Both default to loopback, so a pod exposes
nothing until its deployment sets `address: 0.0.0.0`. Older SDKs ignore the block.

## Upgrade

Rebuild the Knowledge Base image against `fred-sdk[knowledge-base]>=4.4.2`, bind
the endpoints outward in its configuration, expose their ports, and add a scrape
target. No Fred redeployment is required.

## Validation

`curl <pod>:9000/metrics` lists `fred_kb_info` with the definition id and SDK
version. After a run, `fred_kb_runs_total` carries its outcome and
`temporal_activity_schedule_to_start_latency_seconds` is populated on port 9001.
No series carries a team, instance, library, run or user label.

## Rollback

Disable both exporters in the pod configuration, or redeploy the previous image.
No data or schema is involved.

## Limitations

Metrics are Stream 1 only: per definition, for platform operators. Per-instance
follow-up for teams inside Fred is a separate change. Two pods on one host need
distinct ports.
