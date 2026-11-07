---
schema: 1
title: "Optional Zabbix template for Prometheus metrics"
impact: none
configuration: none
configuration_reason: "The added Zabbix template is an optional import; it changes no Fred application or chart setting."
no_action_reason: "A normal Fred deployment does not install this monitoring template, so it requires no operator action."
---
## Applicability

Deployments that choose to monitor Fred with Zabbix.

## Prerequisites

A Zabbix 7.0 instance that can reach each selected `/metrics` endpoint.

## Configuration

The template changes no Fred configuration. Set `{$FRED.METRICS.URL}` separately
on each Zabbix host and make each exporter reachable as described in
`deploy/zabbix/README.md`.

## Upgrade

Deploy Fred normally. Import `deploy/zabbix/fred-prometheus-by-http.yaml` only
if Zabbix collection of Prometheus metrics is wanted.

## Validation

After the import, confirm the HTTP and parsed items are supported and a numeric
metric is discovered on each configured host.

## Rollback

Use the normal Fred rollback procedure. Remove the optional Zabbix template
from monitoring hosts if its collection must be stopped.

## Limitations

The template was not imported into a live Zabbix instance during development.
Each exporter can expose many series, so review the name filter and retention
before applying the template broadly.
