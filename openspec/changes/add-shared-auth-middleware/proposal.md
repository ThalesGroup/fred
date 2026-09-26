## Why

Outbound calls authenticated with service-account tokens need one consistent token-expiry policy across services and SDK clients. The policy is to use the current cached token, refresh and retry once after any first HTTP 401, stop immediately on a first HTTP 403, and share refreshes for the same rejected token.

## What Changes

- Extend the token provider and HTTPX authentication adapter in `fred-pod/security` with the shared policy.
- Use the same adapter for service-account HTTP calls and delegated MCP HTTP transports.
- Accept user access tokens through existing headers and live getters. User-token renewal remains in existing client-specific owners; the shared middleware does not renew user tokens.
- Configure existing service and SDK clients with the adapter; preserve request contents, delegation modes and grants, authorization checks, connection pools, timeouts and streaming behavior.
- Expose the adapter through the public library API so third-party HTTPX clients can attach it. Updated SDK clients use it by default.
- Enable early renewal by default: on token access, renew when 30 seconds or less remain before known expiry. Keep the first-401 retry. Add no cooldown, background timer, configurable retry policy or separate middleware service.

## Capabilities

### New Capabilities

- `outbound-auth-middleware`: Shared cached-token authentication, one retry after a 401, immediate 403 failure, concurrent refresh sharing and library integration.

### Modified Capabilities

None in the main specs. Delegated calls use this policy before terminal authority-error handling.

## Impact

- `fred-pod`: token provider, HTTPX auth adapter and public exports.
- `fred-core`: existing authentication re-exports.
- `fred-runtime`: delegated knowledge-flow, team-wiki, binding and MCP callers, retaining existing user-token behavior.
- `fred-sdk` and backend services: authenticated outbound clients and dependency minimums.
- Delegated-execution acceptance criteria: distinguish a recoverable first 401 from a terminal failure after the allowed retry.

The shared renewal policy applies to backend and SDK service-account HTTP traffic. User-token renewal, browser login, CLI login, external providers' proprietary authentication and Graph-specific behavior are outside this change.
