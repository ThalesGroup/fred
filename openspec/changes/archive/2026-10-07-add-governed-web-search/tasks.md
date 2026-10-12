## 1. Simplify runtime execution

- [x] 1.1 Replace egress deployment fields with direct/default and optional proxy configuration; validate secret/CA fields, update schemas and Helm defaults.
- [x] 1.2 Extract the internal research engine, preserve direct safety and bounded workers, add explicit guarded proxy routing, and delete the Fred egress server.
- [x] 1.3 Call the engine from the attributed runtime adapter; preserve activity/erasure and lifecycle, remove endpoint health polling and wire serialization.

## 2. Deployment and verification

- [x] 2.1 Remove dedicated service examples and dependencies; update migration guide, contracts, dashboard/alerts and package locks for normal Fred startup.
- [x] 2.2 Verify direct native-tool execution, attribution/errors/cancellation, DNS/redirect safety, explicit proxy/no fallback, credential isolation and TLS with focused tests.
- [x] 2.3 Run affected root quality gates, independent read-only review and schema/migration/OpenSpec checks; reconcile this existing change and draft PR #2983.

## 3. Configurable search provider

- [x] 3.1 Add `provider` and `provider_key_env` deployment fields with validation; regenerate schemas; Helm default `brave`.
- [x] 3.2 Implement `fixture` and `brave` providers beside `duckduckgo`; select in `create_engine`; fail startup on a missing key; skip DNS vetting only for fixture results.
- [x] 3.3 Shared provider contract tests (shape, ceilings, errors, key isolation) plus selection/startup tests.
- [x] 3.4 Update migration guide, `.env.template` and Helm values.

## 4. Admin cost and monitoring view

- [x] 4.1 Emit one content-free `web_research.request` KPI event per completed operation (operation, status, error code, team, user, duration, estimated `cost.usd` from `cost_per_1000_searches`).
- [x] 4.2 Add a `web_research_summary` control-plane KPI preset: requests, estimated cost, blocked/busy/failed counts, p95 latency, unique users, outcome breakdown.
- [x] 4.3 Render an admin "Web research" section on the Analytics page with the cost explanation; regenerate the control-plane client.

## 5. Remove the combined tool

- [x] 5.1 Remove `search_and_fetch` (SDK request, engine branch, tool, frontend label, docs): the model chains `web_search` and `fetch_url` itself and reads only useful pages.

## 6. Explicit erasure only

- [x] 6.1 Remove account-deletion erasure fan-out and the per-user erasure fence (store, model, migration, tests); keep the explicit admin erasure endpoint; document it.

## 7. Engine in the runtime

- [x] 7.1 Move the engine and providers into `fred-runtime` with their tests and dependencies; the capability keeps tools and citations; the runtime no longer imports any capability package.

## 8. Long pages

- [x] 8.1 Add `offset` to `fetch_url` and `next_offset` to returned pages; tell the model to use `focus` first and `offset` when the end of the text leads into the relevant part.

## 9. Admin web self-test

- [x] 9.1 Add the `fred.github.self_test_web` probe agent, its Self-test page section and scenario, and exempt its template from the capability gate; enable web research in the local developer configuration.

## 10. Proxy without DNS and clearer errors

- [x] 10.1 In proxy mode, vet only IP literals locally and forward names unresolved; keep direct mode unchanged.
- [x] 10.2 Map proxy tunnel refusals to `proxy_refused`, add a model-facing instruction to each error code, clarify UI labels, count proxy refusals as blocked and accept them in self-test destination probes.

## Evidence

Previous version: 67 focused tests and root quality gates passed; separate egress HTTPS topology was reviewed against implementation head `289b26e509aae586ae5b4b27fbc09a584cfcaf4a`. This is historical evidence, not verification of the revised transport. Current work reuses issue #2980 and branch `codex/add-governed-web-search`.

Proxy assumption: operator-owned HTTP(S) forward proxy with CONNECT and final DNS/destination enforcement, configured explicitly; proxy deployment is outside this change. No public-provider or production proxy validation is claimed.

Provider selection (2026-10-07): 40 capability tests (8 new shared provider contract/selection tests with mocked transports, no live Brave call), 7 runtime web-research tests, ruff and basedpyright clean, `make generate-config-schema`, `make check-config-files` and `helm lint` pass. Local Fred Agents reloaded on the default keyless provider.

Admin view (2026-10-07): runtime KPI emission test (content-free, cost only on successful searches), control-plane preset test (blocked/saturated/failed split, team scope, admin-only), Analytics page tests; full frontend suite 3388 passed, `tsc`/prettier/eslint clean, basedpyright clean on the preset, `check-config-files` and `helm lint` pass. Not verified against a live OpenSearch index.

Explicit erasure (2026-10-07): control-plane erasure fan-out, its test and the runtime per-user fence (model, migration table, store locking, test) removed; 10 runtime web-research/migration tests and 216 control-plane user/delete tests pass (one unrelated Postgres-5433 integration test needs a database not running locally); ruff and basedpyright clean.

Engine in the runtime (2026-10-07): engine, providers and their tests moved with `git mv`; runtime no longer imports any capability (dev dependency and uv source removed, `trafilatura`/`httpcore` in the `app` extra, `dev` includes `app`); redundant end-to-end tool test dropped (adapter and tools stay covered separately). Runtime `make code-quality` 0 errors (5 pre-existing warnings in untouched files) and `make test` 1855 passed; proxy integration test passes; capability `make code-quality` and `make test` (5) pass; Fred Agents loads the runtime engine.

Long pages (2026-10-07): `offset`/`next_offset` engine test (three consecutive slices, last one not truncated) and tool-description test; runtime web-research suites 33 passed, capability 6 passed, ruff and basedpyright clean on the touched modules. Not yet observed on a live page.

Admin web self-test (2026-10-07): the full probe battery passes against the live engine in about 8 s (44 probes); fred-agents self-test agent tests 9 passed; control-plane capability-gate tests 21 passed (new exemption test); frontend pipeline and Self-test page tests 100 passed, `tsc` and prettier clean. Developer ran the page end to end locally after the template exemption.

Proxy without DNS and clearer errors (2026-10-07): DNS-less proxy tests with name lookups failing (fetch and search forward names unresolved; private, numeric and local hosts refused with no connection or lookup; direct mode unchanged), adapter mapping of proxy 403 to `proxy_refused` and 407/5xx to `unavailable`, model-facing error guidance, self-test acceptance of proxy refusals. Before the fix the DNS-less fetch and search tests failed (`unavailable`, 0 results). Runtime web-research suites 60 passed and `make test` 1875 passed; capability 6, fred-agents self-test agent 10, control-plane preset and frontend trace/pipeline/page tests (118) pass. Manual: local squid forward proxy in Docker blocking two sites, DNS disabled in-process: 0 local lookups, blocked sites refused by the proxy, private literals refused by Fred, self-test battery 42/44 passed (the two page-read probes target `example.com`, which that proxy blocked on purpose).

Closing checks (2026-10-07): root `make code-quality` passes on every module (migration-guide tests, Python lint/format/bandit/detect-secrets/basedpyright, frontend `tsc`/prettier/eslint); runtime basedpyright keeps 5 pre-existing warnings in untouched files. `openspec validate --strict` passes. CodeQL substring-URL alerts in tests fixed; stale capability `uv.lock` files refreshed for the runtime extras. Independent read-only review (base `dd1121a7b`, head `9c20d62da` plus working tree) found no blocking issue in direct-mode SSRF; its findings were fixed (proxy 403-only refusal, local refusal of numeric and local hosts behind a proxy) or documented (refused `http://` pages surface as `http_error`, refused provider calls as `provider_failed`). Pre-existing nits left: `response_too_large` is never raised (pages are truncated) and `PublicTransport` replaces its default pool without closing it. Not claimed: live Brave calls, production DMZ/proxy validation, PostgreSQL load, container image build.
