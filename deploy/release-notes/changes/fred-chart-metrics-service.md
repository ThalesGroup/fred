---
schema: 1
title: "Create the fred chart metrics Services from metricsService"
impact: none
configuration: production
configuration_reason: "The chart values bind the exporter of fred-agents, the Knowledge Flow API and the Knowledge Flow worker to 0.0.0.0, and metricsService alone now decides the metrics Service."
no_action_reason: "The chart applies these values itself, so a fresh installation needs no extra operator action."
---
## Applicability

Fresh Fred installations using the `fred` chart.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

Each application with `metricsService.enabled: true` now gets a metrics Service
and `prometheus.io` pod annotations, or a ServiceMonitor when
`metricsService.serviceMonitor.enabled` is also true. By default these are
fred-agents on port 9000, the Knowledge Flow API on 9111 and the Knowledge Flow
worker on 9112. The chart binds their exporters to `0.0.0.0` with
`observability.kpi.prometheus.address`.

To disable this for an application, set `metricsService.enabled: false`. This
removes the Service, the ServiceMonitor and the annotations. The exporter itself
follows `observability.kpi.prometheus` and keeps listening in the pod until that
block changes.

These ports are not authenticated. They stay internal to the cluster as long as
no Ingress exposes them.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Check that `kubectl get service` lists `fred-agents-metrics`,
`knowledge-flow-backend-metrics` and `knowledge-flow-worker-metrics`, then read
`/metrics` through one of them from inside the cluster.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No Prometheus or Zabbix instance was run against these Services during
development.
