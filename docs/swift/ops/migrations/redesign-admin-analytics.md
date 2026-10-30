---
schema: 1
title: "Admin analytics redesign: team-scoped KPI presets, euro costs and Excel export"
impact: minor
configuration: none
configuration_reason: "No chart value or backend configuration key changes; the usd_per_eur display rate (default 1.12) ships in fred-core's packaged model_impact_factors.yaml."
---
## Applicability

Every deployment. Deployments that pin an OpenFGA `authorization_model_id` with schema sync off must act (see Upgrade).

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The OpenFGA model gains `team#can_read_analytics` (team admins) and is written at startup by default; with `sync_schema_on_init: false` and a pinned model id, publish `libs/fred-core/fred_core/security/rebac/schema.fga` first, or team admins are refused. No Alembic migration.

Behaviour changes for API consumers: KPI presets take repeated `team_ids` instead of `team_id`; team-scoped reads need `can_read_analytics`; several presets are removed and costs are reported in euros (`cost_eur`, `estimated_cost_eur`). Full list: `CONTROL-PLANE-PRODUCT-CONTRACT.md` §74. Organization observers now also see storage by team and web research.

## Validation

Open Administration > Analytics as a platform observer: the seven tabs load and "Export" downloads an `.xlsx` workbook.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. API consumers of the removed presets need the previous release.

## Limitations

Capability usage needs the KPI dims of the `kpi-analytics-dims` change and counts only tool calls recorded after it. The user filter covers only users seen since the access rule started recording an attribute.
