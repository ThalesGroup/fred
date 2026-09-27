## Context

See [proposal.md](proposal.md) for the goal and [the spec](specs/outbound-auth-middleware/spec.md) for the token-expiry rule.

Source inspection identifies reusable components: `M2MTokenProvider` and `M2MBearerAuth` live in `fred-pod/security/backend_to_backend_auth.py`; `fred-core` re-exports them and `fred-sdk` depends on `fred-pod`. Existing service clients use HTTPX. The installed MCP HTTP transports accept an `httpx.Auth` instance.

## Goals / Non-Goals

**Goals:** one service-account HTTP authentication implementation, a shared token provider per service identity, and default use by service-authenticated SDK clients.

**Non-Goals:** user-token renewal in the shared middleware, a new HTTP client framework, proxy service, distributed token cache, global credential registry, cooldown, configurable retry count, or Graph-specific code. Connection-pool ownership stays with existing clients.

## Decisions

### Extend the existing authentication adapter

Keep the mechanism in `fred-pod/security`, available through its public exports and existing `fred-core` re-exports. Extend `M2MBearerAuth` around a small provider contract: obtain the current token and refresh the cache entry rejected by a 401. This keeps authentication usable without the agent runtime.

The HTTPX auth flow sends once, handles the first 401, releases that response, obtains the replacement, and yields the same request once more. A first 403 or the retry response is returned to existing error handling. The original request body must remain available for replay, including multipart uploads. Successful response streams remain streamed.

### Keep refresh ownership in the provider

Extend `M2MTokenProvider` using its existing cache and lock. Remember which cache entry a request used. If it has already been replaced, reuse the replacement; otherwise concurrent callers join one in-flight refresh and share its result or failure. A small cache generation distinguishes refreshes even when the issuer returns the same token bytes. Enable early renewal by default: when a token is requested and its known expiry is 30 seconds or less away, renew before sending. Use the same refresh coordination; no background timer or new configuration switch is needed. Early renewal never disables first-401 recovery.

Reuse service-context ownership to pass one provider to clients using the same service identity. Sharing is local to a process and its async lifecycle. User access tokens continue through existing headers and live getters. The shared middleware neither receives a user refresh callback nor acquires, caches or renews a user's token.

Existing user-token recovery stays in its client-specific owners: knowledge-flow request recovery and MCP user-token interceptors and reconnect handling. Ordinary forwarding callers retain their existing error handling. A caller using a user bearer never falls back to a service identity.

### Attach the same adapter to HTTP and MCP

| Integration | Wiring |
| --- | --- |
| Runtime HTTP | Attach auth to delegated `KfBaseClient`, team-wiki and binding requests, retaining grants and run-liveness checks. User-token calls retain existing behavior. |
| Runtime MCP | Supply auth on delegated HTTP connections so connection, listing and invocation use the shared service-token flow. User-token connections retain their existing handling. |
| SDK | Configure service-authenticated control-plane and document clients by default. Remote invocation accepts a service provider or existing caller headers/client authentication. |
| Backend service calls | Pass the existing service-owned provider to scheduled erasure and its outbound cleanup calls. User-triggered calls retain their forwarded identity. |

For service-account calls, only the shared HTTP auth flow owns the authentication retry. Existing client and MCP retry wrappers must not retry a terminal service-token 401/403 again. Delegated terminal-error mapping follows the allowed retry; grants, selected identity and local cancellation checks remain intact. `no_token` connections receive no adapter.

Keep request construction and delegation in their existing owners. Auth integration preserves methods, destinations, query parameters, bodies and non-authentication headers. Delegation switches, grant values, receiver permission and standing checks, timeouts, connection pools and response streaming remain unchanged. A retry reuses the original request with the replacement bearer and rechecks local run liveness after waiting for refresh. It never adds a grant to a non-delegated call or substitutes a service identity for a person.

### Make reuse explicit for library consumers

Service-authenticated SDK clients configure auth by default. A custom asynchronous HTTPX client attaches the public adapter with a shared service-token provider; it needs no copied retry code. User headers and injected client authentication remain supported. Add a short usage example and require dependency versions containing this implementation. No new HTTP wrapper is needed.

## Risks / Trade-offs

- Nested retry handlers can multiply attempts → verify the actual send count through complete client paths.
- User and service credentials have different renewal owners → attach shared renewal only to service-token providers and retain user-token forwarding and existing client-specific recovery.
- Cancellation while awaiting a shared refresh can affect other callers → keep shared refresh ownership separate from an individual request; a cancelled request sends no retry.
- Uploads and streaming transports can lose replayable input → test identical request content and streaming responses with the existing transport mechanisms.
- Request bodies are buffered for an identical retry; large uploads therefore require memory proportional to their body size. Successful response bodies remain streamed.

## Migration Plan

Implement the provider and adapter, then wire the callers above. Align the delegated-execution spec's typed-stop and tool-authentication requirements with this policy: first 401 recovery precedes terminal handling. Release the library and dependent clients together with updated dependency minimums. No schema or deployment-service migration is required; rollback uses the previous compatible package set.
