---
schema: 1
title: "Investigate failed chat turns and LLM invocations in Grafana"
impact: minor
configuration: none
configuration_reason: "The telemetry needs no Fred configuration change. Operators can import the standalone dashboards into an existing Grafana and Prometheus deployment."
---
## Applicability

Operators who use Grafana to monitor Fred chat failures.

## Prerequisites

Use a Prometheus data source that scrapes the Fred agent runtimes and the
backends covered by the Platform health dashboard.

## Configuration

The existing metrics retain their names and gain investigation labels.
Review external queries that join these counters by their complete label
sets. Queries that aggregate by existing labels continue to work.

## Upgrade

Deploy Fred in the usual order. To enable the investigation view, import
the new Chat failure investigation dashboard and re-import Platform health
with the same Prometheus source. See the [Grafana dashboard README](../../../../deploy/grafana/README.md).

## Validation

Follow **Investigate chat failures** from Platform health. Confirm the time
range and filters carry over. Check the failed-turn counts on hover and
inspect the invocation table and HTTP status details over a known event.

## Rollback

Restore the previous Platform health export and remove the investigation
dashboard if it is no longer used.

## Limitations

Older series may lack failure reason, model route, and exact HTTP status.
The dashboard estimates counts from scraped counters. Increments already
included in a series' first scrape may be missed. Invocation coverage is
limited to the instrumented ReAct and Deep model boundary.
