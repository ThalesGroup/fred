# Tasks

## 1. Establish the implementation handoff

- [x] 1.1 Implementation and focused issue publication authorized on 2026-10-20. Tracking #3196, branch `codex/preserve-kf-mcp-failure-diagnostics`, target `swift`; unrelated login-link planning remains excluded.

## 2. Replace copied tool execution with public HTTP customization

- [x] 2.1 Supply the dedicated client through `FastApiMCP(http_client=...)`, implement the transport wrapping `ASGITransport`, and integrate lifespan cleanup; verify forged/duplicate query grants and top-level JSON grants are sanitized, verified grants/context are injected per invocation, unrelated payloads survive, redirects are not followed and the client closes correctly. Preserve existing MCP patches and pin 0.4.0.
- [x] 2.2 Replace the copied executor with a `super()` call and one typed authority-refusal catch; verify 401/403 and marked account-status 503 preserve the exact authority result and runtime stop, unmarked 503 remains ordinary failure, and cancellation/unrelated errors propagate. Verify upstream SQL 400 detail compatibility before removing the bridge's per-tool branch.
- [x] 2.3 Add the async response hook emitting one metadata-only `mcp.inner_http_failure` event for each completed inner status >= 400 before authority conversion; verify severity, registered route/tool metadata, validated response references, retained local context and response-body readability. Verify no success event or invented status for transport exceptions.
- [x] 2.4 Confine restored upstream dependency diagnostics using the existing logging mechanism; verify body, credential, path/query and arbitrary-header canaries remain absent from structured events, dependency records and generic stores, including debug output, independently of traceback rendering.
- [x] 2.5 Extend public-client MCP integration coverage for inner 404 plus outer HTTP 200, upstream detailed error text, malformed/missing references, interleaved scopes, hidden grant schema fields and existing runtime presentation compatibility; verify the production override contains no request construction, result serialization, generic error conversion or per-tool branching.

## 3. Explain empty tabular discovery and expected description failures

- [x] 3.1 Add the small internal typed diagnostic/result structures and collect resolver stage counts during existing work, updating all resolver consumers without changing dataset/alias/attachment semantics; verify existing selection tests and exact authorization/metadata/artifact call counts remain unchanged.
- [x] 3.2 Emit one informational `tabular.discovery_empty` summary for empty listings with the agreed stage reason and bounded counts; verify no-readable-document, empty-authorized-scope, out-of-scope and no-registration cases produce distinct reasons and successful/nonempty discovery adds no such event.
- [x] 3.3 Classify unresolved dataset, incomplete preview and unavailable preview artifact at their actual branches and log `tabular.description_failure` before existing controller conversion; verify distinct safe causes, unchanged 403/404 status/body mappings, no extra I/O and no argument/detail/content leakage with service/controller tests.

## 4. Verify and document the coherent change

- [ ] 4.1 Run the focused cross-boundary tests, affected offline module suites, applicable raw type checks and root `make code-quality` after implementation; record commands/results and actual exclusions in this task file or the PR, keeping formatter work out of the diff.
- [x] 4.2 Update the existing observability guide with event/reason meanings and inner-reference navigation, and add the required English migration note with operational impact `none`; verify it explains restored ordinary MCP error text and the preserved authority contract, agrees with emitted JSON and requires no configuration, package upgrade or HTTP schema change.
- [ ] 4.3 Apply the full branch audit against the actual PR target, obtain the required independent read-only correctness/performance review, resolve findings, and push/open the dedicated draft PR; verify the PR records reviewed base/head, verification and exclusions.
- [ ] 4.4 Reconcile these artifacts with the verified implementation, sync the structured-logging delta and archive through the repository procedures; verify OpenSpec validation and the final shipped requirements match the change.
