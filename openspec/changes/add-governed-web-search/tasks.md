## 1. Simplify runtime execution

- [x] 1.1 Replace egress deployment fields with direct/default and optional proxy configuration; validate secret/CA fields, update schemas and Helm defaults.
- [x] 1.2 Extract the internal research engine, preserve direct safety and bounded workers, add explicit guarded proxy routing, and delete the Fred egress server.
- [x] 1.3 Call the engine from the attributed runtime adapter; preserve activity/erasure and lifecycle, remove endpoint health polling and wire serialization.

## 2. Deployment and verification

- [x] 2.1 Remove dedicated service examples and dependencies; update migration guide, contracts, dashboard/alerts and package locks for normal Fred startup.
- [x] 2.2 Verify direct native-tool execution, attribution/errors/cancellation, DNS/redirect safety, explicit proxy/no fallback, credential isolation and TLS with focused tests.
- [ ] 2.3 Run affected root quality gates, independent read-only review and schema/migration/OpenSpec checks; reconcile this existing change and draft PR #2983.

## 3. Configurable search provider

- [x] 3.1 Add `provider` and `provider_key_env` deployment fields with validation; regenerate schemas; Helm default `brave`.
- [x] 3.2 Implement `fixture` and `brave` providers beside `duckduckgo`; select in `create_engine`; fail startup on a missing key; skip DNS vetting only for fixture results.
- [x] 3.3 Shared provider contract tests (shape, ceilings, errors, key isolation) plus selection/startup tests.
- [x] 3.4 Update migration guide, `.env.template` and Helm values.

## 4. Admin cost and monitoring view

- [x] 4.1 Emit one content-free `web_research.request` KPI event per completed operation (operation, status, error code, team, user, duration, estimated `cost.usd` from `cost_per_1000_searches`).
- [x] 4.2 Add a `web_research_summary` control-plane KPI preset: requests, estimated cost, blocked/busy/failed counts, p95 latency, unique users, outcome breakdown.
- [x] 4.3 Render an admin "Web research" section on the Analytics page with the cost explanation; regenerate the control-plane client.

## Evidence

Previous version: 67 focused tests and root quality gates passed; separate egress HTTPS topology was reviewed against implementation head `289b26e509aae586ae5b4b27fbc09a584cfcaf4a`. This is historical evidence, not verification of the revised transport. Current work reuses issue #2980 and branch `codex/add-governed-web-search`.

Proxy assumption: operator-owned HTTP(S) forward proxy with CONNECT and final DNS/destination enforcement, configured explicitly; proxy deployment is outside this change. No public-provider or production proxy validation is claimed.

Provider selection (2026-10-07): 40 capability tests (8 new shared provider contract/selection tests with mocked transports, no live Brave call), 7 runtime web-research tests, ruff and basedpyright clean, `make generate-config-schema`, `make check-config-files` and `helm lint` pass. Local Fred Agents reloaded on the default keyless provider.

Admin view (2026-10-07): runtime KPI emission test (content-free, cost only on successful searches), control-plane preset test (blocked/saturated/failed split, team scope, admin-only), Analytics page tests; full frontend suite 3388 passed, `tsc`/prettier/eslint clean, basedpyright clean on the preset, `check-config-files` and `helm lint` pass. Not verified against a live OpenSearch index.
