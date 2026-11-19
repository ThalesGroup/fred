---
schema: 1
title: "Hide KPI pages and widgets when no OpenSearch KPI store is configured"
impact: none
configuration: none
configuration_reason: "KPI availability is derived from the existing observability.kpi.opensearch sink; no configuration key or default changes."
no_action_reason: "Deployments with an OpenSearch KPI store see no change; deployments without one stop showing empty KPI surfaces after a normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release, mainly those running
without an OpenSearch KPI store.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Without an OpenSearch KPI store: verify that Admin › Analytics and the team
usage page are no longer listed (platform admins included), that the home
page has no activity tab, and that the self-test skips its KPI steps.
With an OpenSearch KPI store: verify these surfaces are unchanged.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A Prometheus or log KPI sink alone still does not enable these pages: they
read KPI presets from OpenSearch only.
