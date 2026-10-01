---
schema: 1
title: "Read structured frontend access logs"
impact: minor
configuration: none
configuration_reason: "The frontend image selects JSON access logs automatically; no new deployment setting or collector container is required."
---
## Applicability

Production nginx frontend container. Vite and browser JavaScript logging are outside this change.

## Prerequisites

Keep the existing nginx image/runtime and pod stdout/stderr collection. Review native-text retention and access policies before deployment.

## Configuration

No new variable or Helm setting is required. Access events use escaped JSON stdout with bounded route families; native errors/startup and entrypoint messages retain text on their existing streams.

## Upgrade

Deploy the updated frontend image. Update saved access-log queries/parsers to use `http_status`, `http_route`, `duration_s` and `severity`. The local nginx `request_id` is separate from API response references.

## Validation

Run the existing rendered-config smoke and container smoke with the updated image. Check 2xx/4xx/5xx JSON, event time, per-request IDs and omission of adversarial paths, queries, credentials, cookies and bodies. In GKE, separately verify severity/timestamp promotion and field filtering, then examine a native startup/upstream failure. A local container check does not establish managed-collector parsing.

## Rollback

Restore the previous frontend image and its access-log parser. No data migration or application configuration rollback is needed.

## Limitations

Native nginx errors can include raw request lines/queries and upstream/file details; entrypoint theme/configuration messages remain text. These are not sanitized by the JSON access format. Native collector parsing and GKE severity/timestamp promotion remain unverified rollout checks. No browser telemetry or extra JSON conversion container is added.
