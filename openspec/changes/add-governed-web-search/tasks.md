## 1. Simplify runtime execution

- [x] 1.1 Replace egress deployment fields with direct/default and optional proxy configuration; validate secret/CA fields, update schemas and Helm defaults.
- [x] 1.2 Extract the internal research engine, preserve direct safety and bounded workers, add explicit guarded proxy routing, and delete the Fred egress server.
- [x] 1.3 Call the engine from the attributed runtime adapter; preserve activity/erasure and lifecycle, remove endpoint health polling and wire serialization.

## 2. Deployment and verification

- [x] 2.1 Remove dedicated service examples and dependencies; update migration guide, contracts, dashboard/alerts and package locks for normal Fred startup.
- [x] 2.2 Verify direct native-tool execution, attribution/errors/cancellation, DNS/redirect safety, explicit proxy/no fallback, credential isolation and TLS with focused tests.
- [ ] 2.3 Run affected root quality gates, independent read-only review and schema/migration/OpenSpec checks; reconcile this existing change and draft PR #2983.

## Evidence

Previous version: 67 focused tests and root quality gates passed; separate egress HTTPS topology was reviewed against implementation head `289b26e509aae586ae5b4b27fbc09a584cfcaf4a`. This is historical evidence, not verification of the revised transport. Current work reuses issue #2980 and branch `codex/add-governed-web-search`.

Proxy assumption: operator-owned HTTP(S) forward proxy with CONNECT and final DNS/destination enforcement, configured explicitly; proxy deployment is outside this change. No public-provider or production proxy validation is claimed.
