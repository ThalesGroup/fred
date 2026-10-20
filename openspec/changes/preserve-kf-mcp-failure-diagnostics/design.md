# Design

## Context

See proposal.md for motivation. The current `DelegatedFastApiMCP._execute_api_tool` copies request construction and result handling from upstream, but discards most failures with `RuntimeError("Tool request failed.") from None`. Its authority-refusal and curated `read_query` 400 branches return earlier. The pinned `fastapi-mcp==0.4.0` already accepts a public `http_client` constructor argument and ordinarily logs/re-raises errors containing the tool name, HTTP status and response text.

`RequestLoggingMiddleware` already gives each inner route fresh local IDs and returns them as `X-Request-ID` and `X-Correlation-ID`. Existing access logs retain only status, route and timing. Tabular service exceptions distinguish unresolved datasets and preview readiness, but the controller maps both to 404 without an operation-level cause record. A shared resolver serves listing, description and queries; it currently exposes no stage summary explaining an empty listing.

Existing structured-logging requirements govern metadata-only output and admitted identity. The runtime consumes `structuredContent={"cause": "authority_lost"}` before adapter conversion to stop a run. HTTPX cannot construct that MCP result, and 0.4.0 has no public error-result mapping hook. Preserve this contract through one minimal compatibility override; the rest uses public interfaces.

## Goals / Non-Goals

**Goals:** Remove duplicated tool execution, retain inner HTTP evidence independently of tracebacks, preserve verified-grant/context handling and authority stops, and explain tabular failures and empty listings using existing resolved work.

**Non-Goals:** Agent-side logging or error presentation changes; a new error protocol; per-tool error mappings; package upgrades or upstream contributions; changed HTTP route payloads, retries, authority checks or context admission; formatter work; resolving the historical workbook bug. Restoring upstream MCP error text is an explicit effect of reusing its executor, not a change to agent presentation policy.

## Decisions

### Use the public HTTP client interface for request customization

Provide a dedicated `httpx.AsyncClient` through `FastApiMCP(http_client=...)`, with a custom `AsyncBaseTransport` wrapping `ASGITransport`. Keep the existing base URL, timeout and `raise_app_exceptions=False` behavior, set `follow_redirects=False`, and own/close the client and wrapped transport in Knowledge Flow's application lifespan. Do not modify shared-client defaults per call or affect unrelated HTTP clients and existing MCP compatibility patches.

Sanitize reserved grant names (`person`, `run`, `agent`) in the serialized query, including duplicates, and top-level JSON object body before dispatch. Apply only the mount-verified grant, using canonical query parameters so inner authentication sees one complete trusted source. Preserve unrelated parameters and body fields, valid framing and original non-JSON payload behavior. Keep grant fields hidden from tool schemas. Read the verified grant and logging context inside each invocation; never cache them on the transport or client. Replace any supplied context header with trusted outbound context under the existing admission rules.

Leave OpenAPI argument mapping, HTTP method dispatch, ordinary result serialization and ordinary failure conversion to upstream. Compared with retaining the copied executor or overriding both private methods, this confines most custom behavior to documented extension points. No upgrade is needed: 0.4.0 already provides the required constructor interface.

### Keep one private wrapper for the authority-result contract

The response hook logs the actual failed response first. For HTTP 401/403 or HTTP 503 carrying the existing account-status-unavailable denial marker, raise one private typed exception containing no response body or credentials. A minimal `_execute_api_tool` override calls `super()` with the original invocation parameters and catches only this exception, returning the existing authority-refusal `CallToolResult` unchanged. Upstream may log and re-raise the exception before this catch; the dedicated structured response event remains authoritative for the HTTP evidence.

The override must not construct requests, inject grants, serialize results, catch generic tool errors or branch on tool names. Preserve cancellation and unrelated exceptions. Ordinary failures regain upstream MCP status/detail reporting. Verify the existing `read_query` HTTP 400 consumers against that upstream envelope, then remove its special branch from the bridge; the curated detail remains produced by Knowledge Flow. No agent/runtime production code changes are planned.

### Log the HTTP response before MCP conversion

Register one async HTTPX response hook on the dedicated client. For completed inner responses with status >= 400, emit one `mcp.inner_http_failure` event: warning for 4xx, error for 5xx. Read the body with `await response.aread()` before any body inspection and leave it available to upstream. Use ordinary Python logging and structured `extra`; do not log the response object or arbitrary response text. The event retains registered `tool_name`, safe `upstream_route` template, method, `upstream_http_status`, and valid `upstream_request_id`/`upstream_correlation_id` from the response, without replacing locally bound request/correlation fields. Validate references against the locally generated UUID format; omit invalid values.

Obtain route/operation metadata from the registered inner ASGI route and carry it in invocation-local transport metadata to the hook; use registered operation metadata to identify the MCP tool. Never infer a template from a concrete URL or log its path/query. Missing route metadata remains absent. Success adds no response-failure event. The inner access log remains authoritative for HTTP completion; the response event joins outer and inner references. Transport exceptions without a completed response remain exceptions, not invented HTTP statuses, and diagnostic processing must not mask the original operation failure.

The hook event is metadata-only; safe business detail comes from the closed tabular reasons below. Reusing upstream also reintroduces its body-bearing exception and concrete-path debug message. Route the relevant dependency diagnostics through the existing dependency-confinement mechanism so raw bodies, paths, grant values and exception strings do not leak into logs or stores. Keep the explicit Fred event informative and do not depend on the separately investigated traceback formatter. The upstream MCP result and confined log record are separate outputs.

### Keep tabular classification at the business branch

In the tabular feature, use a small internal typed classification for existing unresolved-dataset and preview failures, preserving the existing exception inheritance, strings and controller mappings. Classify preview-read `FileNotFoundError` at the catalog read boundary and re-raise compatibly. The description controller emits a structured `tabular.description_failure` warning with `reason` before its existing HTTP conversion. Keep classifications independent of string parsing; do not log raw exception/detail strings.

Use `datasets_not_resolved`, `preview_not_ready` and `preview_artifact_unavailable` as the closed expected reasons. Permission refusals must retain existing authorization behavior and must not reveal guessed document existence through new diagnostics. Do not bind model-provided document/library lists as trusted context; reuse available admitted/resolved fields, and omit document identity when it was not resolved.

### Summarize resolution without additional I/O

Accumulate a small internal resolution summary while the existing resolver performs authorization, scope intersection and descriptor expansion. Preserve all current authorization branches, including service-agent and attachment behavior. Keep this concern in a focused tabular diagnostics module rather than extending the already-large service with a separate logging subsystem. All resolver consumers must retain their existing dataset semantics; discovery uses the summary to emit one informational `tabular.discovery_empty` event when its document list is empty.

Use nonnegative counts of metadata observed through existing authorized-folder/ownership lookups, scoped metadata and resolved tables, excluding known document denials. Current targeted lookups already apply scope before returning candidates, so these are observed counts, not a global pre-scope readable-document census; obtaining the latter would violate the no-extra-I/O requirement. Classify a known `empty_authorized_scope` first, then unscoped `no_readable_documents`, `no_documents_in_scope` or `no_registered_tables`. Preserve the list-returning resolver API and pass an optional invocation-local typed summary for discovery; all existing consumers keep their dataset semantics. Reuse validation helpers and existing context budgets; log counts and classifications rather than metadata, column schemas, raw selectors or files. No extra storage/authorization calls, per-document log flood, success-path bridge event, new metrics or label dimensions.

### Test through public interfaces and actual MCP calls

Extend the mounted receiver tests in Knowledge Flow and `libs/fred-runtime/tests/test_delegation_receiver_integration.py`, plus shared-core grant/context tests. Construct the server with its public custom client and exercise MCP client calls instead of relying only on direct private-method tests. Assert that an inner 404 carried by outer HTTP 200 produces one structured failure event with its receiver reference and a standard detailed MCP error. Verify unchanged authority stops, curated SQL 400 detail, response readability, and omitted invalid/missing references. Keep current agent presentation checks as compatibility coverage without changing that policy.

Cover forged/duplicate query grants, top-level JSON grants, missing verified grants, unrelated payload preservation, hidden tool fields, context-header replacement, redirect rejection, interleaved invocations, cancellation and client cleanup. Verify non-authorization HTTP 503 remains an ordinary tool failure. A synthetic public-interface feasibility probe passed query/body grant handling, context forwarding, hook readability and route metadata, detailed 404 reporting and disabled redirects; it confirmed the missing authority marker without the wrapper. It did not validate full authentication admission or concurrency.

Extend Knowledge Flow's tabular tests for stage counts and the three expected description causes, with no-extra-I/O assertions. Capture structured fields independently of tracebacks. Canary checks cover new events and upstream dependency records under real logging setup, including debug level and generic stores; response bodies may reach MCP as upstream error text but must not enter generic diagnostics.

## Risks / Trade-offs

- Moving from arguments to serialized requests adds query/body framing risk. Keep rewriting limited to reserved grant fields, preserve unrelated data, and test both wire locations through real MCP calls.
- The remaining override depends on private upstream behavior. Keep it limited to the typed authority translation and pin/test 0.4.0; a future public result hook can replace it separately.
- Restored upstream errors contain response text and its logging may expose it. Apply existing dependency confinement and test all configured sinks independently of traceback rendering; record the intentional MCP error-text change in migration guidance.
- Resolver changes could affect queries or attachment authorization. Preserve dataset selection/alias behavior, reuse existing fixtures, and require independent review of affected consumers.
- Counts and valid references must remain metadata-only. Validate references locally, keep reasons closed, and test malicious bodies/headers/arguments and concurrent scope restoration.
- Empty discovery is legitimate and may be frequent. Emit one informational summary only for empty discovery; no per-document or all-success expansion.

## Migration Plan

No configuration, database migration, operator action, package upgrade or HTTP response-schema regeneration is intended. Add the required English migration note with operational impact `none`, describing restored ordinary MCP error text and the preserved authority marker. Document event/reason meanings and a GCP query example in the existing observability guide. Deploy the updated shared-core/KF images normally. Rollback restores the prior bridge and removes the new diagnostics without modifying documents, stored conversations or authorization state.
