---
schema: 1
title: "Optional Zabbix template for Prometheus metrics"
impact: none
configuration: none
configuration_reason: "The added Zabbix template is an optional import; existing Fred application and chart settings are unchanged."
no_action_reason: "Normal Fred deployment does not install this monitoring template, so existing deployments need no migration action."
---
## Applicability

Existing Fred deployments upgrading to this release, including deployments
without Zabbix monitoring.

## Prerequisites

No prerequisites for the Fred upgrade. Operators adopting the template need a
Zabbix 7.0 instance that can reach each selected `/metrics` endpoint.

## Configuration

No Fred configuration changes are required. For an optional Zabbix import, set
`{$FRED.METRICS.URL}` separately on each host as described in
`deploy/zabbix/README.md`.

## Upgrade

Deploy Fred normally. Import `deploy/zabbix/fred-prometheus-by-http.yaml` only
if Zabbix collection of Prometheus metrics is wanted.

## Validation

Existing deployments need no additional validation. After an optional import,
confirm the HTTP and parsed items are supported and a numeric metric is
discovered on each configured host.

## Rollback

Use the normal Fred rollback procedure. Remove the optional Zabbix template
from monitoring hosts if its collection must be stopped.

## Limitations

The template was not imported into a live Zabbix instance during development.
Each exporter can expose many series, so review the name filter and retention
before applying the template broadly.
