---
name: add-kpi-to-dashboard
description: Extend Fred analytics for an agreed user question by reusing existing emitters, queries, API clients and chart components. Verify current Weaver support before implementing a dashboard change.
---

# Extend existing analytics

Read `AGENTS.md` and the relevant arc42 operations explanation. Start with the
user decision the metric supports, its meaning and authoritative data source.
Find the existing emitter, aggregation, query, API and UI consumers before
adding anything. Reuse or extend the shared path and identify redundant charts
or metrics it replaces. Do not add a metric merely because data is available.

Inspect the active checkout. Control Plane is Rust in `apps/control-plane`;
retired Python KPI preset instructions do not establish a current endpoint.
Trace the actual route/schema and `apps/frontend/src/rework/components/pages/admin/AnalyticsPage/`.
If support is missing, state the smallest required backend adaptation in the
agreed increment; never invent a working hook or restore a retired backend.

For persistence changes, use `fred-reconstruction-method` before API/UI design.
Explain rows scanned, query selectivity, aggregation windows, retention and
bounded response sizes. Reuse existing exporters, metric naming and labels;
avoid secrets, document contents and unbounded identifiers in telemetry. Do not
introduce a second data authority, cache or index without a concrete need.

When a public schema changes, regenerate the owning OpenAPI and frontend client
using current Makefile targets. Do not hand-edit generated clients. Reuse existing
API enhancements and shared chart molecules, loading/empty/error behavior, design
tokens and both locales. Verify actual response shapes and component props rather
than copying a historical recipe.

Run affected-component code-quality checks. Only run a live query, browser check
or functional test within the requested validation scope, against the selected
environment with existing secure credentials; never embed credentials in a skill
or command. Report reused mechanisms, removed paths, actual checks and remaining
gaps. A successful compilation alone does not establish useful or accurate data.
