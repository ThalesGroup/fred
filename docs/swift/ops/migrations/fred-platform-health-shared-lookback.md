---
schema: 1
title: "Share the chat and HTTP lookback on the platform health dashboard"
impact: none
configuration: none
configuration_reason: "Only the standalone Grafana dashboard export changes. It uses the existing Prometheus data source and metrics."
no_action_reason: "The Fred upgrade does not manage imported Grafana dashboards or change telemetry. Operators can re-import the dashboard independently."
after: [fred-platform-health-dashboard]
---
## Applicability

Operators who use the Fred platform health dashboard in Grafana.

## Prerequisites

Use a Prometheus data source that collects Fred chat-turn and HTTP metrics.
See the [Grafana dashboard README](../../../../deploy/grafana/README.md).

## Configuration

No Fred configuration changes are required.

## Upgrade

Deploy Fred normally. To update the Grafana dashboard, optionally re-import
the dashboard JSON and select the existing Prometheus data source.

## Validation

Select a time range with chat turns and HTTP traffic. Change **Lookback** to
**1h** and check that the chat failure rate, turn volume, and HTTP 5xx rate
update. The two chat tooltips should show the same failed and total counts at
the same timestamp. The chat rate chart also shows a fixed 24-hour reference.

## Rollback

Re-import the previous dashboard export.

## Limitations

The charts depend on available Prometheus data. The turn counts are estimates
computed from scraped counters.
