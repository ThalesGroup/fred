## 1. Shared authentication

- [x] 1.1 Extend the token provider with refresh for a rejected cache entry and default renewal on access at 30 seconds before known expiry. Verify both sides of that boundary, concurrent early renewal, first-401 recovery after early renewal, one refresh for concurrent and delayed 401s, same-value token renewal, and separate identities using deterministic tests.
- [x] 1.2 Extend the HTTPX auth adapter and public exports. Verify the response matrix (success, 401 then success, 401 then 401, 401 then 403, first 403), exact attempt counts, plain 401 handling, identical replayed payloads and streamed responses.

## 2. Client integration

- [x] 2.1 Wire delegated knowledge-flow, team-wiki and binding calls to shared service-token auth. Verify service recovery, unchanged request contents and grants, authorization and cancellation checks, user-token forwarding and preserved client-specific user recovery. Verify the shared middleware never invokes user refresh callbacks.
- [x] 2.2 Attach shared service-token auth to delegated MCP HTTP connections. Verify connection, listing and invocation recovery, terminal service-token failure without an outer retry, and preserved user-token and unauthenticated connection behavior.
- [x] 2.3 Wire service-authenticated SDK and backend clients identified in the design. Verify default service recovery, unchanged forwarded-user headers and injected client authentication, and public adapter imports without the agent runtime.

## 3. Delivery and verification

- [x] 3.1 Set dependency minimums to the release containing the middleware and add a short service-token usage example. Verify package metadata, public imports and documentation of the user-token boundary.
- [x] 3.2 Align delegated-execution typed-stop and tool-authentication requirements and their tests with first-401 recovery followed by terminal error handling. Verify no acceptance scenario requires a first 401 to be fatal.
- [x] 3.3 Run repository-root quality checks and affected tests, review service-refresh concurrency and cancellation, and record the actual results and remaining validation limitations.
