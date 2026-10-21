---
schema: 1
title: "Fred chart: register applications and Knowledge Base publishers by id, under registrations"
impact: minor
configuration: production
configuration_reason: "The fred chart now derives the control plane's platform.application_sources and knowledge_bases.publishers, and the frontend's FRONTEND_APPLICATIONS_JSON, from the new registrations value, and refuses values that still set them. Overlays that register applications or publishers must move those entries before upgrading; bundled values register nothing and need no edit."
---
## Applicability

Deployments of the fred chart whose values register an application (`applications.control-plane-backend.configuration.platform.application_sources`, or `FRONTEND_APPLICATIONS_JSON` in `applications.frontend.env` or `extraEnvVars`) or a Knowledge Base publisher (`applications.control-plane-backend.configuration.knowledge_bases.publishers`). Docker Compose configuration is unchanged.

## Prerequisites

The overlay values that register applications and publishers, to rewrite before the upgrade.

## Configuration

Move each `application_sources` item to `registrations.applications.<app_id>`: the item without its `app_id`, plus a `gateway` holding that application's `FRONTEND_APPLICATIONS_JSON` entry without its `app_id` (`ui_upstream`, and `service_upstream`, `service_required` when set). Move each publisher to `registrations.knowledgeBasePublishers.<client_id>: {prefix: <prefix>}`. Then delete the former keys, and the `FRONTEND_APPLICATIONS_JSON` entry of the frontend's env:

```yaml
registrations:
  applications:
    acme-forecast:
      ui_prefix: /apps/acme-forecast
      version: 1.0.0
      display_name: { en: "Forecast" }
      description: { en: "Demand forecasting." }
      gateway:
        ui_upstream: http://acme-forecast-ui.acme-apps.svc.cluster.local:80
        service_upstream: http://acme-forecast-api.acme-apps.svc.cluster.local:8000
        service_required: true
  knowledgeBasePublishers:
    kb-acme: { prefix: acme.kb }
```

These are maps, so each application's entry can live in its own values file. A later file sets an entry to `null` to remove it.

## Upgrade

Rewrite the values as above, then deploy Fred normally. A chart render that still finds a former key fails and names its `registrations` replacement, before any resource changes.

## Validation

Render the chart with the rewritten values (`helm template`). The control plane's ConfigMap lists the same `application_sources` and `publishers` as before the upgrade, and the frontend's `FRONTEND_APPLICATIONS_JSON` the same gateway entries, ordered by id. After deployment, each team's Apps page shows the same applications.

## Rollback

Restore the previous chart with the previous values. The rendered configuration is the same, so no data or state is involved.

## Limitations

The chart validates each entry's fields. The gateway URLs are still checked by the frontend container at start, and publisher prefix overlaps by the control plane at start.
