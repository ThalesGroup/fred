---
schema: 1
title: "Add the Fred platform health Grafana dashboard"
impact: none
configuration: none
configuration_reason: "The repository adds a standalone dashboard export that uses existing Prometheus metrics."
no_action_reason: "The Fred upgrade leaves Grafana dashboards, scrape configuration, and stored metrics unchanged."
---
## Applicability

Operators who want a Grafana overview of chat turns and backend HTTP health.

## Prerequisites

To use the dashboard, follow the data-source requirements in the
[Grafana dashboard README](../../../../deploy/grafana/README.md).

## Configuration

No Fred configuration changes are required.

## Upgrade

Deploy Fred normally. Importing the dashboard in Grafana is optional and
independent of the Fred upgrade.

## Validation

After importing, select a time range with chat turns and HTTP traffic.
Check that the summary cards populate and both error-rate controls update the
failed-turn and HTTP 5xx charts.

## Rollback

Remove the imported dashboard from Grafana if it is no longer needed.

## Limitations

Panels can only show metrics available in the selected Prometheus data source.
