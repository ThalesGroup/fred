## Purpose

Give backend services, SDK clients and third-party consumers one consistent policy for service-account token renewal while preserving existing user-token forwarding and client-specific recovery.

## ADDED Requirements

### Requirement: Each call uses the current cached token

Every outbound call authenticated by a service-account provider SHALL use that provider's current cached token. A client or connection SHALL NOT keep sending a service token captured before its shared cache was updated. The renewal requirements below apply to service-account tokens, including delegated calls.

#### Scenario: Another call updates the token

- **GIVEN** two clients sharing one credential identity
- **WHEN** one client refreshes the cached token and the other starts a call
- **THEN** the new call uses the updated cached token

### Requirement: A first 401 refreshes and retries once

The first HTTP 401 for a service-account call SHALL be treated as token expiry. The client SHALL refresh the token and retry the same call exactly once. This SHALL apply to every such 401, without requiring expiry wording in headers or the body. The retry SHALL preserve the method, destination, payload and delegation parameters; only the bearer token changes.

#### Scenario: A plain 401 is recovered

- **WHEN** a call receives 401 with no expiry information and token refresh succeeds
- **THEN** the same call is sent once more with the refreshed token and its result is returned

### Requirement: A retry cannot start another auth retry

If the retry returns HTTP 401 or 403, the client SHALL surface the error and SHALL NOT refresh or send another attempt. Nested client layers SHALL NOT restart the authentication retry sequence for that call.

#### Scenario: The retry is refused

- **WHEN** the initial call returns 401 and the retry returns 401 or 403
- **THEN** the caller receives the error after exactly two outbound attempts, with no further refresh

### Requirement: A first 403 stops immediately

A first HTTP 403 SHALL be surfaced immediately. It SHALL NOT cause a token refresh or a retry.

#### Scenario: Access is forbidden

- **WHEN** the initial call returns 403
- **THEN** the caller receives the error after one outbound attempt and no refresh

### Requirement: Concurrent 401 responses share a refresh

Concurrent calls rejected with 401 for the same cached token SHALL share one refresh. A delayed 401 from that group SHALL reuse the replacement already obtained rather than trigger another refresh. Different credential identities SHALL NOT share tokens or refresh results.

#### Scenario: Several requests reject the same token

- **GIVEN** several concurrent calls sent with the same cached token
- **WHEN** they receive 401, including one response arriving after the refresh completes
- **THEN** one token refresh serves the group and each call retries at most once with the replacement

#### Scenario: Separate identities refresh

- **WHEN** calls for two distinct credential identities receive 401
- **THEN** each identity refreshes independently and uses only its own token

### Requirement: Early renewal is enabled by default

On service-token access, the provider SHALL renew by default when 30 seconds or less remain before the token's known expiry. Early renewal SHALL use the same shared refresh coordination and SHALL NOT replace the first-401, retry-limit, first-403 or concurrent-refresh requirements above.

#### Scenario: A call reaches the early-renewal window

- **GIVEN** the default provider settings and a cached token with known expiry
- **WHEN** a call requests the token with 30 seconds or less remaining
- **THEN** the provider renews before the call is sent, sharing that renewal with concurrent callers

#### Scenario: A cached token is outside the early-renewal window

- **WHEN** a call requests a cached token with more than 30 seconds remaining
- **THEN** the provider reuses it without proactive renewal, while retaining recovery if the call receives 401

#### Scenario: A recently renewed token is rejected

- **GIVEN** the cache renewed a token before its known expiry
- **WHEN** the next call receives its first 401
- **THEN** that call still follows the refresh-and-retry-once policy

### Requirement: Authentication integration preserves requests and delegation

Apart from the token acquisition and HTTP 401/403 handling specified above, integration SHALL preserve request methods, destinations, query parameters, bodies, non-authentication headers, timeouts and response streaming. It SHALL preserve delegation switches, selected identity, grant values, receiver permission and standing checks, and local run-liveness and cancellation checks. Refresh SHALL NOT change the identity used for a call.

#### Scenario: A delegated request is retried

- **WHEN** a delegated request receives 401 and is retried after refresh
- **THEN** its original person, run and agent grant values and request content are preserved, with only the bearer replaced
- **AND** existing authorization and run-liveness checks still apply

#### Scenario: Delegation is disabled

- **WHEN** a call uses a user access token with delegation disabled
- **THEN** it retains that user identity, carries no delegation grant and follows the existing client-specific token handling

### Requirement: User-token renewal stays outside the shared middleware

User access tokens SHALL remain usable through existing authorization headers and live token getters. The shared middleware SHALL NOT acquire or refresh user tokens, invoke user refresh callbacks, or proactively renew user tokens. Existing client-specific user-token refresh and error-handling behavior SHALL remain unchanged. A user-token call SHALL NOT acquire a service token as a fallback.

#### Scenario: A forwarded user token is rejected

- **GIVEN** a caller forwarding a user access token without a client-specific renewal mechanism
- **WHEN** the receiver returns 401
- **THEN** existing error handling receives the response without shared-middleware renewal or retry

#### Scenario: An existing client owns user-token recovery

- **GIVEN** a client with an existing user-token refresh callback
- **WHEN** its existing recovery condition is met
- **THEN** that client-specific recovery remains responsible for the refresh
- **AND** the shared service-token middleware does not invoke the callback or add another retry

### Requirement: Services and library consumers use the same behavior

Backend and SDK service-account HTTP calls SHALL use the shared policy, including delegated calls and delegated HTTP tool connection, listing and invocation. Delegated calls SHALL apply terminal authority-error handling only after the permitted 401 recovery, or immediately for a first 403.

Updated SDK clients configured with service credentials SHALL provide this behavior by default. The library SHALL expose a public authentication adapter for third-party service-token clients. Installing the library alone SHALL NOT be represented as configuring an independently constructed client.

#### Scenario: SDK consumer receives recovery by default

- **WHEN** an application uses an updated SDK client with service credentials and its request receives 401
- **THEN** the client performs the shared recovery without application-written retry code

#### Scenario: Custom client attaches the adapter

- **WHEN** a third-party client uses the public adapter and a shared service-token provider
- **THEN** it receives the same expiry and concurrent-refresh behavior

#### Scenario: A delegated tool call recovers

- **WHEN** an HTTP tool call receives 401 and succeeds on its single retry
- **THEN** the call succeeds with its original delegation parameters and the run continues
