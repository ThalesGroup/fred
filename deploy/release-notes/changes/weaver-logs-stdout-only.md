---
schema: 1
title: "Write every Fred log to stdout in one format; remove the direct OpenSearch log store"
impact: minor
configuration: production
configuration_reason: "storage.log_store is removed from the agent, Knowledge Flow and worker configurations and from the chart schemas, which now refuse it; the monitor takes MONITOR_LOG_LEVEL and MONITOR_LOG_FORMAT instead of RUST_LOG"
---
## Applicability

Deployments of Fred agents, Knowledge Flow, its worker, Control Plane or the monitor.

## Prerequisites

Stdout must reach whatever the operators read. k3d ships it with Fluent Bit and GKE with
Cloud Logging. Fred's chart installs no collector: a platform without one keeps logs in
`kubectl logs` only.

## Configuration

Remove `storage.log_store` from every values and configuration file: the chart schemas
refuse this key. `storage.opensearch` stays when vector search or KPI use it. An OpenSearch
identity may lose its rights on the application-log index. Existing log indexes are neither
read nor deleted by Fred.

The chart defaults now set `MONITOR_LOG_LEVEL` and `MONITOR_LOG_FORMAT`; an override of
`RUST_LOG` on the monitor has no effect.

## Upgrade

Deploy Fred normally once the key is removed.

Log consumers must read the common fields: `severity`, `timestamp` (`seconds`, `nanos`),
`message`, `logger`, `service`, `service_role`, `category` and the source location. Three
streams change shape. Python audit lines on `fred.security.audit` lose `ts`, `level`, `msg`
and `extra`, whose fields move to the top level. Knowledge Base pod lines lose `ts`, `level`,
`msg`, `file`, `line` and `exc`. Monitor lines become the common format. In text mode, the
source reads `service/role/logger`.

Ad hoc `[TAG]` message prefixes are gone: filter on `logger` instead. `[SECURITY]` and
`[KPI]` remain.

Code built on `fred_core` must stop passing `store=` to `log_setup`, must pass
`service_role`, and must stop importing the removed log store classes and configurations.

## Validation

Read one line of each deployed process in your log tool: each carries `service`,
`service_role` and `severity`. On k3d, `log_json.service` is set in `k3d-logs-*` and no
write reaches the old application-log index.

## Rollback

Restore `storage.log_store` together with the previous release. No application data is
migrated. Lines written meanwhile stay in the collector's index only.

## Limitations

Logs written during the release no longer reach the old index, and old entries are not
copied to the collector's index. A line over the collector's own limit can be dropped; on
k3d, Fluent Bit skips long lines.
