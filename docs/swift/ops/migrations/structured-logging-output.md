---
schema: 1
title: "Select structured JSON output for Fred APIs"
impact: minor
configuration: production
configuration_reason: "app.log_format selects json or text in the three API models and deployed chart reference values explicitly select json."
---
## Applicability

Control Plane, Knowledge Flow and hosted Fred agent APIs. This first slice covers output; request, delegated-call and worker correlation follow in later slices.

## Prerequisites

Use the matching code and chart release. Custom stdout parsers must accept the new JSON fields.

## Configuration

Set `app.log_format: json` in API configuration to emit one JSON object per stdout line. The chart reference selects JSON. Omitted values and local examples select `text`; selection is independent of the optional generic log store. Existing log-store DTOs remain compatible.

## Upgrade

Reconcile production overlays with the chart values and restart the APIs. Adapt stdout queries to `severity`, `message`, `timestamp`, `logger`, `service` and `service_role`. The timestamp contains event-creation epoch seconds and nanoseconds. The audit stream retains its existing isolated JSON representation.

Shared configuration startup events retain the selected file paths as structured `env_file` and `config_file` fields, rather than embedding them in the message. Environment-file contents are not logged.

Dependency warnings/errors retain their logger, severity and safe scoped context,
but use a fixed diagnostic message without upstream text, extras or tracebacks in
every delegation mode. They remain console-only to avoid recursive store emission.

## Validation

Emit an ordinary event and confirm that stdout has a complete single-line JSON object with normalized severity, event time, source and structured properties. Verify severity/timestamp promotion and field filtering in a GKE canary before declaring collector compatibility. Check readable local output without width-dependent wrapping.

## Rollback

Set `app.log_format: text` and restart if a parser needs the prior readable workflow, or roll back the paired code/chart. No data migration is introduced.

## Limitations

No GKE deployment or canary was performed during offline verification. Native processes outside Python do not use this formatter. Configuration-load statuses are buffered until the selected formatter is available; invalid/unavailable configuration can still produce bootstrap failure output before a valid logging setting exists. This slice does not yet provide ingress/journey scopes, trusted downstream propagation, or worker handoff. Dependency warning/error events are console-only to avoid recursive store emission.
