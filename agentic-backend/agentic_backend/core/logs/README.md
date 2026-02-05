# Logs module

## Purpose

- Expose a small FastAPI controller to serve chat/UI log queries over the configured LogStore (RAM in dev, OpenSearch in prod).
- Keep log access behind the same auth model as KPIs (Keycloak + authorize_or_raise), not a raw Grafana/OpenSearch endpoint.

## Scope & rationale

- Thin controller only delegates querying to ApplicationContext-selected store (`get_log_store()`), avoiding coupling the UI to any vendor.
- Provides an MCP-friendly route shape (`/logs/query`) mirrored after the KPI controller for consistency.
- Not a full observability stack; meant for “agent/user facing logs” in the product UI. Deep ops/infra stays in Grafana/OTel.

## When to extend

- Add filters or pagination fields to `LogQuery` in `fred_core` if the UI needs them.
- Implement additional routes here only if they’re product-facing; keep ops-only endpoints in your observability tooling.
