---
schema: 1
title: "Knowledge Base pods name themselves and expose operational metrics"
impact: none
configuration: local
configuration_reason: "libs/fred-runtime/fred_runtime/app/config.py now takes the app.runtime_id pattern from fred-pod; the key, its pattern, its default and the generated agent-pod schema are byte-identical, so Fred's chart values are unaffected. Only a Knowledge Base pod's own configuration.yaml gains the required app.runtime_id and the optional observability keys."
no_action_reason: "Fred deployments are unaffected. A Knowledge Base image is affected only once rebuilt against fred-sdk 4.4.2, and its own deployment then sets app.runtime_id."
---
## Applicability

Knowledge Base images built on `fred-sdk[knowledge-base]` 4.4.2 or later. Fred's
own applications and chart are not affected. The `app.runtime_id` model moves to
`fred-pod`, where agent pods (`fred-runtime`) and Knowledge Base pods share it;
agent pods see no change. The `fred-sdk` patch release refreshes the local
lockfiles of every project that depends on it by path.

## Prerequisites

No prerequisites for Fred. A Knowledge Base deployment that wants to be scraped
needs Prometheus, and the Prometheus Operator CRDs if it uses a ServiceMonitor.

## Configuration

**Breaking for Knowledge Base pods:** `app.runtime_id` is required — a lowercase
slug such as `webdav-kb`, chosen per deployment, the key agent pods already use.
A pod rebuilt on 4.4.2 without it exits at startup naming the key. It becomes
the `service` label of every series and the `service` field of every log line.

**Breaking for Knowledge Base code:** `KnowledgeBaseSyncResult.reconciliation_complete`
(a boolean) is replaced by `reconciliation` (`complete`, `partial` or
`up_to_date`, `KnowledgeBaseReconciliation`). `True` becomes `complete`, `False`
becomes `partial`; a run that proves its source unchanged reports `up_to_date`.
Fred's applications never read this field.

Optional, under `observability`: `kpi.prometheus` (`fred_kb_*` series, port 9000),
`temporal.prometheus` (`temporal_*` series from the workflow engine, port 9001)
and `logs.format` (`json`, the default, or `text`). Both endpoints default to
loopback, so a pod exposes nothing until its deployment sets `address: 0.0.0.0`.
An enabled endpoint whose port is taken stops the pod at startup. Older SDKs
ignore all of these keys.

## Upgrade

Add `app.runtime_id` to the pod configuration (in chart values when the chart
renders it), rebuild the image against `fred-sdk[knowledge-base]>=4.4.2`, bind
the endpoints outward, expose their ports and add a scrape target. Logs on
standard output become JSON lines; adjust any log parsing that expected text.
No Fred redeployment is required.

## Validation

`curl <pod>:9000/metrics` lists `fred_kb_info` with `service` set to the runtime
id, the definition id, `sdk="fred-sdk-python"` and the SDK version. After a run,
`fred_kb_runs_total` carries its outcome and
`temporal_activity_schedule_to_start_latency_seconds` on port 9001 carries the
same `service`. A log line of that run has `"service": "<runtime id>"`. No series
carries a team, instance, library, run or user label.

## Rollback

Redeploy the previous image; the new configuration keys are ignored by older
SDKs. No data or schema is involved.

## Limitations

Metrics are Stream 1 only: per pod and definition, for platform operators.
Per-instance follow-up for teams inside Fred is a separate change. Two pods on
one host need distinct ports.
