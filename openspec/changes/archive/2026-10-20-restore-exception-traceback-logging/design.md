# Design

## Context

See proposal.md for motivation and boundaries. `ProcessorFormatter` transfers standard-library exception information to the incoming event and clears the copied record before invoking `EventProcessor`. Fred currently checks the cleared record, so even a correct application `logger.exception` loses its traceback. A separate Uvicorn filter overwrites server warnings/errors and clears diagnostic fields before either formatter runs. The generic FastAPI handler adds a third, detail-free event for an uncaught failure.

`RequestLoggingMiddleware` owns a mutable-lifetime snapshot populated by trusted business admission/resolution and already uses it for completion. An isolated probe with a real middleware task boundary found that the generic handler's ambient context retained only request/correlation IDs, while completion's owned snapshot retained user/session/agent/team as well. Merely changing that handler to `logger.exception` does not reliably meet the correlation requirement. Waiting for Uvicorn loses even the request context and has been rejected by the developer.

The shipped `structured-logging` safeguard currently requires metadata-only diagnostics and broad sensitive-data confinement. The requested policy deliberately relaxes that rule for ordinary application/server exception text; the delta makes this explicit rather than claiming that a URL regex guarantees arbitrary-message confidentiality. The nearby MCP/tabular change intentionally excludes this work.

## Goals / Non-Goals

**Goals:** Preserve normal exception diagnostics in JSON and readable stdout, apply the existing known-pattern URL redaction consistently, and give the common uncaught request path one exception owner alongside its completion owner. Both events must be searchable through the same available admitted references, including across middleware task boundaries and under concurrency.

**Non-Goals:** Changing the optional generic store, audit schema, dependency filter, runtime support-reference mechanism, incoming context admission, HTTP payloads or statuses; adding local-variable dumps, a new configuration switch, a general secret classifier, a global log-and-rethrow deduplication mechanism, or extending request-context lifetimes beyond their owning request. Other delegation-driven logging changes await a separately agreed scope.

## Decisions

### Read exception information at the formatter's supported seam

In `EventProcessor`, read `event.get("exc_info")`, pass present information to the existing exception renderer and retain its formatted `exception` field. Remove the delegation check at this site. Keep `ProcessorFormatter`'s default record-clearing behavior: enabling `keep_exc_info` instead could make Python append a second raw traceback after the rendered JSON. Preserve the original log record and continue deriving source, severity and trusted context through the existing path.

### Keep targeted redaction and remove blanket Uvicorn suppression

Remove the branch in `UvicornSensitiveQueryFilter.filter` that replaces access/server messages and calls `_clear_unrestricted_diagnostic_details`. Keep this filter responsible only for targeted sanitization of string messages and string positional arguments, including normal formatting behavior. Duplicate suppression belongs in the separate filter described below. Do not remove `_clear_unrestricted_diagnostic_details` itself: the separate dependency filter still uses it and is outside scope.

Use one shared implementation of the existing token-query and invitation-path substitutions. Move it to a small logging helper if needed, since `log_setup.py` already imports `processors.py` and importing the sanitizer back from setup would introduce a cycle. Apply the same helper to the final formatted exception string, including visible chained exceptions. Sanitizing only `record.msg` and `record.args` leaves `exc_info` exception messages untouched; the synthetic probe confirmed that exact leak. Preserve all other ordinary diagnostic text and standard traceback formatting. This does not enable automatic locals, bodies or headers.

### Log at the request boundary using its authoritative snapshot

Remove only `logger.error("Unhandled request failure")` from the generic handler. Preserve its exception-type KPI bookkeeping and existing generic JSON 500 response. Starlette sends that response and explicitly re-raises the original exception.

Catch that failure in `RequestLoggingMiddleware`, before exiting its owned scope, and emit the exception with a separate application exception logger. Bind `owner.values` using the same snapshot-emission mechanism as completion (`completion_log_scope`), rather than relying only on ambient `current_context`. This preserves every available validated bound field, not a new hardcoded identity allowlist. It also prevents retired child-task bindings from either losing identity or reintroducing explicitly cleared values. Re-raise the original exception after reporting it; preserve the existing HTTP outcome, cancellation and disconnect classifications. Application `OSError` failures must remain reportable without turning client disconnects into new application-error traces.

Keep the existing separate HTTP completion event, including ERROR for 5xx, termination timing, route templates, outcome and response reference headers. Both records must carry the same request-owned user/session/agent/team and request/correlation fields when those have been admitted/resolved. Missing identity before admission remains absent; do not read it from headers or unverified credentials. A controller that logs an exception and then raises a handled `HTTPException(500)` still owns its diagnostic and does not reach this uncaught-error path. An explicit HTTP 500 without a logged underlying exception has only completion. This slice does not deduplicate arbitrary application code that logs and then re-raises an uncaught exception.

### Suppress only the server's duplicate of an already reported exception

After the boundary emits its exception diagnostic, associate a private in-process reported marker with that exact exception before re-raising it. Use a shared small helper or equivalent shared private sentinel so the request boundary and Uvicorn filter agree without a circular import. The marker carries no business identity, is not serialized, and needs no process-global registry or retention of request context.

A dedicated minimal `AlreadyReportedExceptionFilter` inspects `record.exc_info` and returns false only when its exception satisfies `was_reported`. It does not rewrite the record, sanitize strings, inspect delegation or depend on message/severity matching. Attach it to `uvicorn.error`, before the separate URL sanitization filter, and include it in repeated-setup replacement so initialization cannot stack duplicate filters.

An unmarked exception, a different exception with identical text, a server failure outside this request boundary or a lifecycle warning still follows normal targeted sanitization and output. Do not walk arbitrary causes to suppress a different top-level failure. This replaces unconditional server suppression with duplicate prevention tied to an actual request-boundary report. Concurrency tests must verify that one request cannot suppress another request's diagnostic.

## Risks / Trade-offs

- Ordinary exception text can contain sensitive values outside recognized URL patterns. Mitigation: preserve the known redactions, add reproductions for each identified leak, and document this as targeted redaction rather than universal sanitization. This is the developer-requested policy change.
- Ambient context at the error handler can lose child-task business references. Mitigation: use the request-owned completion snapshot and assert equality of all available identity fields on exception and completion, including child-task and interleaved failures followed by a fresh request.
- Overbroad deduplication could hide a distinct server failure. Mitigation: suppress only the exact exception marked after a boundary report; verify unmarked failures, identical-message distinct exceptions and independent concurrent requests remain visible.
- Existing tests explicitly assert blanket message/traceback removal. Mitigation: replace those assertions only for the scoped application/server behavior, while retaining audit, dependency, admission and context-isolation checks.
- Rendering a traceback can break JSON framing or duplicate text if implemented at the wrong layer. Mitigation: test the real logging setup, visible chains, multiline content and both renderers; retain one physical line for each JSON event.

## Migration Plan

Update the observability guide and add the required operator migration note describing restored exception text, the unchanged response contract, the targeted redaction policy and request-boundary ownership with correlated identity. Operators should find request exception traces with their existing identity filters; server failures outside a request retain only their available context. Deploy the updated shared library through the normal backend image rollout; no configuration or database migration is needed. Existing log-based rules that relied on the fixed server message or `uvicorn.error` as the request exception owner need review. Rollback is the previous library/image version, which restores the former suppression. Live GKE collection remains a rollout check, separate from local formatter/request-flow verification.
