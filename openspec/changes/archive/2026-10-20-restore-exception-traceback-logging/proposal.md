# Proposal

## Why

Fred currently loses exception tracebacks in its shared formatter and replaces Uvicorn error details with a fixed message. Operators need the exception diagnostic alongside the HTTP completion event with the same available user/session/agent/team and request/correlation references, in either delegation mode, so their production filters reliably find both events.

## What Changes

- Read exception information from Structlog's event dictionary and render it without a delegation-based suppression check.
- Stop rewriting Uvicorn error messages and clearing their exception, stack and event details. Retain the existing targeted URL credential/invitation redaction and apply it to rendered exception diagnostics as well as Uvicorn messages and arguments. Use a separate minimal duplicate-exception filter to suppress only the server report of an exception already reported by the request boundary.
- Log an uncaught exception inside Fred's request middleware using the same request-owned context snapshot as completion, then re-raise it with a private reported marker for duplicate suppression. Keep the generic HTTP exception handler responsible for its existing response and KPI bookkeeping; remove its detail-free error log.
- Retain the separate ERROR-level HTTP completion event for 5xx responses, without adding a second traceback there.
- Replace the existing blanket restriction on these exception diagnostics with ordinary exception messages and traceback frames plus known-pattern redaction, independently of delegation. This is an explicit relaxation of the current diagnostic-confinement policy, not a guarantee that arbitrary exception text contains no sensitive information.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `structured-logging`: Preserve correlated exception diagnostics with targeted redaction and define separate exception/completion ownership for ordinary request failures.

## Impact

The main changes are in `libs/fred-core/fred_core/logs/processors.py`, `logs/http.py`, `logs/log_setup.py` and `common/fastapi_handlers.py`, with shared redaction/reporting helpers as needed to avoid duplication or circular imports, focused tests, the observability guide and an operator migration note. No HTTP payload, status, KPI, authorization, configuration, generic-store, audit or dependency-logging change is intended.

Uvicorn currently logs after Fred's request context closes. That context-free ownership was rejected: the request boundary now owns the correlated exception event before context closes. Both events must retain all available admitted references, including across middleware task boundaries; missing or unadmitted references are not invented. Exceptions that the request boundary has not reported remain eligible for normal server logging.

Tracking: [#3190](https://github.com/ThalesGroup/fred/issues/3190), related to [#2906](https://github.com/ThalesGroup/fred/issues/2906). The active `preserve-kf-mcp-failure-diagnostics` change explicitly excludes the formatter and serves a distinct MCP/tabular diagnostic outcome; it is not modified. Broader delegation-driven suppression outside the two named logging sites remains outside this proposal, pending the author's explanation.
