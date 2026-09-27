## Verified behavior

- Service-token cache access, default renewal at the 30-second boundary, and one retry after a first 401.
- Immediate first-403 failure and terminal handling after a retry returns 401 or 403.
- Shared service renewal for concurrent and delayed 401s, including same-value token replacement and isolated credential identities.
- Cancellation of one caller leaves shared renewal available to other callers; delegated calls recheck run liveness.
- Replay preserves request content and grants, including consumed asynchronous and multipart bodies. Successful response streams remain streamed.
- User tokens use existing headers and live getters without shared renewal or service-identity fallback. Existing knowledge-flow request recovery and MCP user-token interceptors and reconnect handling remain responsible for user recovery.
- SDK clients preserve forwarded-user headers and injected client authentication when no service-token provider is supplied.
- Scheduled erasure retains its failure receipt and session metadata when service-token acquisition or renewal fails.

## Test evidence

Repository-root `make code-quality` passed across all configured modules against the final source. Both affected OpenSpec changes passed strict validation, and `git diff --check` passed.

The final affected suites ran from the repository root with Python 3.12 and Node 22.13.0. The checks used `MAKE='make -o dev -o node_modules'`, `UV_NO_SYNC=1` and `UV_OFFLINE=1` to reuse installed dependencies. Local socket fixtures had loopback access.

| Suite | Result |
| --- | --- |
| Pod library | 69 passed |
| Core library | 962 passed; 36 integration cases deselected |
| SDK | 490 passed; 3 skipped |
| Runtime | 1,418 passed; 3 skipped; 16 integration cases deselected |
| Agent application | 77 passed |

These suites total 3,016 passing tests. The focused service-token provider and auth tests cover the response matrix, shared renewal, early renewal, request replay and cancellation. User-path regressions cover forwarding near known expiry, a forwarded first 401, existing knowledge-flow refresh, and MCP connection retries without shared service auth.

Ten direct delegated HTTP and remote-SSE probes passed: success, 401 then success, 401 then 401, 401 then 403, and first 403 through each integration. They verified attempt counts, preserved grants, payloads, non-authentication headers and timeouts. Direct erasure probes verified bounded failed-store results after renewal failure.

## Review and limitations

Independent standards and specification reviews found no remaining verified defect in the service-only implementation. Concurrency review covered shared refresh, cancellation, credential ownership and run liveness. This is source and offline-test evidence, not a measured production performance result.

The full root test gate has two existing macOS failures in unchanged code:

- `apps/knowledge-flow-backend/tests/features/scheduler/test_extraction_process.py::test_a_child_that_ended_by_itself_does_not_leave_its_descendant`
- `apps/knowledge-flow-backend/tests/processors/input/pdf_markdown_processor/test_pdf_markdown_processor.py::test_pdf_child_timer_drops_when_channel_is_full`

The first leaves a descendant process alive; the second receives `ENOBUFS` from a full channel instead of the expected exception. These failures remain outside this implementation. Runtime receiver integration tests requiring the unavailable `fastapi_mcp` package were skipped. No live identity-provider deployment or load test was run.

Header-only user calls retain their existing error handling. They do not acquire a service identity, enter shared renewal, or gain a new user refresh mechanism.
