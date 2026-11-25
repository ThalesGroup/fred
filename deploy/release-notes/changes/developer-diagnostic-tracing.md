---
schema: 1
title: "Configure experimental diagnostic tracing through Fred YAML"
impact: minor
configuration: local
configuration_reason: "Local diagnostic tracing now selects the YAML backend and Collector endpoint instead of process activation/export environment variables."
---
## Applicability

Developer environments using the experimental Weaver OTel instrumentation and
conversation benchmark. Ordinary deployments keep diagnostic export disabled.

## Prerequisites

Matching Fred and deployment-factory checkouts, with a reachable OTel Collector.
This is a developer diagnostic facility, not a production tracing service.

## Configuration

Select `observability.tracer: diagnostic` and
`observability.diagnostic.collector_endpoint` (the full OTLP HTTP traces URL) in
both Control Plane and Agent Pod YAML configurations. The factory supplies
persistent Collector YAML settings and an application VALUES overlay; see its
[recipe](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/docs/BENCHMARKS.md#diagnostic-traces).
Remove `FRED_OTEL_ENABLED`, `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
and sampler overrides used by the old recipe. The selected YAML backend, fixed
service identity and parent-based sampling replace those settings.

## Upgrade

Redeploy the prepared development services through the ordinary procedure.
Thereafter, choose diagnostic or performance mode in bench without restarting
Fred between campaigns. Preserve unrelated credentials and KPI settings.
Standalone Langfuse configuration remains separate and unchanged.

## Validation

With diagnostic YAML selected, bench diagnostic mode should retrieve technical
spans correlated to its turns. Requests without a sampled W3C parent, including
performance mode's default, must not create diagnostic exports. Check the reported
coverage; missing spans are not zero-duration operations. No prompt, answer,
identity or Langfuse observation metadata should appear in diagnostic spans.

## Rollback

Disable diagnostic selection and redeploy normally. Returning to earlier images
requires their earlier configuration contract; no SQL migration is involved.

## Limitations

Instrumentation and delivery are partial. Sampling context is not authentication;
any client can request traces in a prepared development environment. Queues are
bounded and asynchronous but tracing has a cost. Production incident retention
and tail sampling are outside this feature. Existing raw trace files are not
retroactively sanitized.
