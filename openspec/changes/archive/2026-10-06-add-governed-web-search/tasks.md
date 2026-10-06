## 1. Contracts and capability

- [x] 1.1 Define retention, reader roles, erasure and the provider in the observability/product contracts; document deployment privacy/provider approval as an activation prerequisite.
- [x] 1.2 Add a typed web-research port to the SDK/runtime services and a first-party capability package with bounded tools and configuration; register the entry point without editing registry hot spots.
- [x] 1.3 Verify enablement, per-call authorization, ReAct/Deep/Graph parity and bounded tool outputs with focused tests.

## 2. Egress service and deployment

- [x] 2.1 Define/version the authenticated HTTPS operation schema; implement the Fred adapter and an egress service with provider adapter, extraction, timeouts and limits.
- [x] 2.2 Test DNS/connection pinning, IPv4/IPv6 filtering, redirects, credentials, response bounds, provider failures and unavailable DMZ endpoint.
- [x] 2.3 Add portable configuration and examples for local, Docker/Podman, VM split-DMZ and Kubernetes; document TLS, service credentials, network policy, secrets and rollback/disable behavior.

## 3. Activity and operations

- [x] 3.1 Implement a restricted, durable activity sink with one record per request, query/URL handling, correlation, configurable 30-day default purge and user erasure; test access, failure and deletion paths.
- [x] 3.2 Reuse standard content-free tool audit and metrics; add web operation counts/latency/failure, egress health and operator alerts/dashboard examples. Verify query text and credentials never enter ordinary logs/metrics/audit.
- [x] 3.3 Run focused integration tests in both local and split-service topology, root quality gates and an independent review; record evidence and remaining operator prerequisites in this task list before applying/archiving the spec.

## Verification and review evidence

- Tracking: #2980; branch `codex/add-governed-web-search`, based on `origin/swift` (`dd1121a7b258c7be89777a19fa8ee0b1ac7b3e2c`).
- Native capability/egress: 22 tests passed, including a real HTTPS native-tool integration with a trusted private CA and rejection without that CA. Graph tool artifacts and ReAct/Deep middleware use the same native tools.
- Runtime activity: 6 tests passed; real packaged migration ancestry/SQLite upgrade: 3 passed. Restricted read/erasure authorization endpoints: 2 passed. Existing account-deletion routes and fanout: 24 passed. Pod capability discovery: 10 passed. Total focused verification after rebase: 67 tests passed.
- Helm values validation, strict OpenSpec validation and migration-guide check passed. Root `make code-quality` passed for all 17 modules across resumed runs; all seven affected modules were rechecked successfully after rebase. Type findings were corrected without adding baseline suppressions.
- Independent read-only author/performance review covered SDK/native tools, runtime binding, outbound transport, provider, retention/erasure, monitoring, migration, packaging and deployment consumers. Findings were corrected: provider bypass/SafeSearch, shared cookies, blocking focus, late insertion after erasure, Unicode wire limits, and intentional refusal reported as a storage outage. The removed Brave adapter made its region parsing finding unreachable.
- Final independent review compared base `dd1121a7b258c7be89777a19fa8ee0b1ac7b3e2c` with implementation head `289b26e509aae586ae5b4b27fbc09a584cfcaf4a`, including regenerated consumers. No remaining supported findings. Rebase preserved upstream MCP packaging, user avatar cleanup, and runtime contracts; the subsequent lock-only commit aligns the SDK dependency metadata.
- Exclusions: no live public-provider/CNI/production-DMZ or PostgreSQL concurrency/load campaign. HTTPS split-service verification uses a real local socket and deterministic public-provider fixture. Operator activation still requires privacy/provider acceptance, TLS/service secrets, migration and network policy configuration; none is claimed provisioned by this change.
