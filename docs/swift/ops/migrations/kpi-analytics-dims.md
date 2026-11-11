---
schema: 1
title: "KPI events carry the tool's capability and the API request's team, with an optional backfill"
impact: minor
configuration: none
configuration_reason: "No chart value or backend configuration key changes; the new KPI fields are added to the OpenSearch mapping at startup."
---
## Applicability

Every deployment. The optional backfill only matters to deployments with KPI history in OpenSearch.

## Prerequisites

None. For the backfill: a control-plane pod that reaches OpenSearch and PostgreSQL, as at runtime.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. At startup the KPI store adds `dims.capability_id`, `quantities.cache_read_tokens` and `quantities.tool_count` to the existing index. No Prometheus label is added. No Alembic migration.

Optional activation: complete past events once, dry run first.

```bash
kubectl exec deploy/<control-plane> -- fred-control-plane-kpi-backfill --dry-run
kubectl exec deploy/<control-plane> -- fred-control-plane-kpi-backfill
```

`--since <ISO date>` limits the range; `--step reindex|teams|all` (default `all`). The team step is safe to rerun and skips events that already have a team. The reindex step rewrites every selected turn event on each run, so use `--step teams` when retrying team attribution alone.

## Validation

The backfill logs `updated N turn event(s)` and `updated N event(s) for M user(s)`. A second `--step teams` run reports 0 events. A second reindex run reports the selected turn events again.

## Rollback

Use the normal rollback procedure. The added fields and backfilled `dims.team_id` values are ignored by the previous release.

## Limitations

Backfilled team attribution is a per-UTC-day estimate. Tool calls recorded before the upgrade get no capability. Avoid running the backfill during user deletions; on large platforms the team step can take hours (`--since` helps).
