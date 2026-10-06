## Why

Revise #2980 / draft PR #2983 before delivery. The dedicated HTTPS egress process makes local testing and deployment unnecessarily complex. The user requests an internal implementation that starts with Fred alone and can later use an operator-owned DMZ forward proxy.

## What Changes

- Execute search, extraction and focus inside Fred Agents through the existing SDK port. Reuse the three tools, authorization, restricted activity store, erasure and metrics.
- Use direct public Internet access when enabled without a proxy. Support an explicitly configured HTTP(S) forward proxy for all research traffic, with no fallback to direct access.
- Remove the Fred egress HTTP server, its token, TLS listener, health polling and service deployment examples. Local activation requires only `web_research.enabled: true`.
- Preserve bounded requests, direct DNS connection pinning, redirect checks, SafeSearch and verified origin TLS. Document the proxy's responsibility for final DNS resolution and destination enforcement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-research`: internal execution and direct-or-proxy outbound routing; monitoring uses existing Fred metrics.

## Impact

Reuse the current capability package and runtime adapter. Rename the egress implementation to an internal research engine and delete its server-specific code. Update SDK deployment configuration, schemas, package extras/locks, Helm values, operator guide and dashboard/alerts. Keep activity SQL and account erasure unchanged. No Knowledge Flow API, new migration, new deployment, or new user flow.

## Out of Scope

Designing/deploying the operator's proxy, authenticated website browsing, arbitrary model headers, proxy TLS interception, and changes to unrelated outbound Fred traffic.
