## MODIFIED Requirements

### Requirement: The iframe SDK exposes a framework-independent public contract

The `@fred-oss/iframe-sdk` archive SHALL expose its child client from `.` and the shared protocol wire contract from `./protocol` as ESM JavaScript and closed TypeScript declarations. The child client SHALL expose `onContext(listener: (context: FredApplicationContext) => void): () => void` in addition to its existing connection, route, navigation, open-chat, request, and disposal API. It MUST NOT depend on React, React DOM, `@fred-oss/ui`, `@fred-oss/design-tokens`, FRED application state, routing libraries, Keycloak, translation catalogs or runtimes, backend models, or consumer-specific code. Undocumented deep imports MUST remain blocked.

#### Scenario: A neutral TypeScript consumer imports both entry points

- **WHEN** an application with no framework dependency imports the documented client API, `onContext`, and protocol types from the packed archive
- **THEN** type checking and production bundling succeed without React, another FRED package, a deep import, or access to FRED source

#### Scenario: A consumer requests an internal module

- **WHEN** a consumer attempts to import a generated or internal SDK module
- **THEN** the package export map prevents that module from becoming public API

### Requirement: Connection admission is explicit and bounded

The client SHALL require an explicit HTTP(S) host origin and expected application ID. It SHALL install its listener before sending `fred:ready`, post only to that exact origin and `window.parent`, and accept messages only when `event.origin` equals the configured origin and `event.source` equals `window.parent`. On the protocol-`"1"` compatibility path, a valid initial `fred:context` MUST carry protocol version `"1"`, the expected application ID, and the complete cloneable team, route, and locale context before the client becomes connected. An omitted optional theme from an older host SHALL be accepted without manufacturing a theme; a present theme MUST be `"light"` or `"dark"`.

`connect()` SHALL send `fred:ready` immediately and retry at a fixed bounded cadence until it connects or reaches a default 10-second connection deadline. Concurrent calls SHALL share the same connection lifecycle. A missing parent, malformed initial context, unsupported protocol, application-ID mismatch, deadline, or disposal MUST fail actionably rather than becoming a silent connection. A malformed or misattributed later context MUST NOT replace the last accepted context or notify subscribers.

#### Scenario: A configured child completes the handshake

- **WHEN** the expected parent answers a ready announcement from the configured origin with a valid matching context
- **THEN** connection resolves once with that context and handshake retries stop

#### Scenario: A ready announcement races host setup

- **WHEN** the first ready announcement is not observed but the host becomes available before the connection deadline
- **THEN** a bounded retry permits connection without creating a second client lifecycle

#### Scenario: A message comes from the wrong source or origin

- **WHEN** a structurally valid initial or later host message comes from another window or a different origin
- **THEN** the client ignores it without connecting, changing context, navigating, notifying subscribers, or settling a request

#### Scenario: Context names another application

- **WHEN** the configured parent sends an initial context whose application ID differs from the client's expected identity
- **THEN** connection fails with an application-mismatch error and no operational host message is accepted

#### Scenario: The host never completes the handshake

- **WHEN** no valid matching context arrives within the connection deadline
- **THEN** connection rejects, retries and timers stop, and operational methods remain unavailable

#### Scenario: An older host omits theme

- **WHEN** the new SDK receives a valid initial protocol-`"1"` context containing team, route, and locale but no theme
- **THEN** connection succeeds, `client.context.theme` remains absent, and the consumer retains responsibility for its own fallback policy

#### Scenario: Initial context has an invalid theme

- **WHEN** an otherwise valid initial context includes a theme other than `"light"` or `"dark"`
- **THEN** the parser rejects it and connection fails as malformed context

#### Scenario: A later context fails admission

- **WHEN** a connected client receives malformed context, invalid theme, wrong application ID, or unsupported protocol from the expected parent and origin
- **THEN** its last accepted context and pending work remain intact, and no context subscriber is notified

### Requirement: Context, route, and navigation APIs preserve host ownership

The connected client SHALL expose the latest accepted context and separate context- and route-event subscriptions. The first valid context SHALL resolve `connect()` once. Every accepted later `fred:context` message, including an identical repeat, SHALL replace `client.context` with a validated immutable snapshot and be delivered once to each context subscriber current when that message is handled. `onContext` SHALL return an unsubscribe function; it SHALL NOT replay the initial context automatically or reset consumer business state. A throwing context listener MUST NOT prevent the context update or delivery to another listener; listener exceptions SHALL be reported under the same isolation policy as route subscribers. Disposal SHALL clear both subscriber sets and reject further operations.

The client SHALL deliver each accepted `fred:route` message exactly once to each route subscriber that is current when the message is handled. It MUST NOT deduplicate accepted route messages solely because their `subPath` equals a previously delivered value. A context update MUST NOT implicitly emit a route event. The client SHALL send only relative `fred:navigate` intents with explicit replace semantics and `fred:open-chat` with a string session candidate or `null`. Relative path validation MUST reject absolute, schemed, fragmented, malformed, backslash, and single- or multiply-encoded traversal paths before posting while the host remains authoritative.

The SDK MUST NOT inspect or mutate the parent DOM, select a FRED route outside the application subtree, resolve a chat destination, infer team identity, derive a missing theme from FRED internals, or own consumer translation state. Deployment-owned `hostOrigin` configuration remains separate from live context; iframe URL query parameters MUST NOT become the authoritative theme/locale synchronization mechanism.

#### Scenario: The host changes the application route

- **WHEN** a connected client receives a valid `fred:route` message from its accepted parent and origin
- **THEN** every current route subscriber receives the host-owned sub-path once

#### Scenario: Navigation returns to a previously delivered route

- **WHEN** the host sends route A, the child requests navigation to B, and the host later sends route A again
- **THEN** every subscriber current for each host message observes A and then A again, with neither accepted route event suppressed by sub-path deduplication

#### Scenario: A consumer requests application navigation

- **WHEN** a connected consumer supplies a valid relative path and replace choice
- **THEN** the client sends the existing normalized `fred:navigate` shape without choosing the resulting FRED route

#### Scenario: A consumer opens chat with no trusted destination

- **WHEN** a consumer calls open-chat with an optional session candidate
- **THEN** the client sends only that candidate and the host retains all destination and authorization decisions

#### Scenario: A path attempts to escape

- **WHEN** a consumer supplies an absolute, schemed, fragmented, malformed, or traversing path to navigation or request
- **THEN** the client rejects it locally and sends no message

#### Scenario: Later context updates the latest snapshot

- **WHEN** a connected client receives valid light-to-dark, dark-to-light, or locale-A-to-locale-B contexts from the accepted parent
- **THEN** `client.context` reflects each latest accepted snapshot and every current context subscriber receives each update once without another connection or consumer business-state reset

#### Scenario: Identical contexts are events, not deduplicated values

- **WHEN** the accepted parent repeats a valid context with identical team, route, locale, and theme values
- **THEN** every current context subscriber receives that later message once while `connect()` stays settled and route subscribers receive no synthetic route event

#### Scenario: Unsubscription and listener failure are isolated

- **WHEN** one context subscriber unsubscribes and another throws while a later valid context arrives
- **THEN** the unsubscribed listener is not called, the throwing listener is reported without preventing the remaining listeners from receiving the context, and the latest context remains available

#### Scenario: Disposal ends live delivery

- **WHEN** a client is disposed before a later context, route, or request reply arrives
- **THEN** no context or route subscriber runs, and existing request/disposal behavior remains unchanged

#### Scenario: Iframe query parameters are not live context

- **WHEN** an iframe URL includes `?theme=dark&locale=fr` but the accepted host context carries other resolved values or later changes
- **THEN** the SDK exposes only the accepted host context as FRED's theme and locale truth, while `hostOrigin` remains independently configured

## ADDED Requirements

### Requirement: FRED publishes resolved live application context

The FRED host SHALL derive an effective `"light"` or `"dark"` theme from its existing theme owner, including system preference when selected, and SHALL send that resolved value with its current locale in the initial `fred:context`. While the same authorized frame is connected, the host SHALL resend the existing `fred:context` shape with current team and route plus resolved theme and locale when either resolved value changes. It MUST preserve the existing team-switch frame remount, source/origin checks, authorization boundary, route authority, request lifecycle, and host-only bearer/refresh behavior. A child MUST NOT need to inspect FRED DOM, Redux, storage, authentication state, or translation catalogs to learn the resolved values.

#### Scenario: Initial resolved theme is light or dark

- **WHEN** an authorized application frame completes its handshake while FRED resolves either light or dark theme
- **THEN** the initial context contains that resolved theme, the current locale, and the existing team and route fields, without exposing `"system"` or implementation state

#### Scenario: The effective theme changes in either direction

- **WHEN** FRED's selected or system-resolved theme changes light-to-dark or dark-to-light while the frame remains connected
- **THEN** the same frame receives a new valid context with the effective theme and current locale without a second messaging system or frame reload

#### Scenario: The FRED locale changes

- **WHEN** FRED changes its active resolved locale while the frame remains connected
- **THEN** the same frame receives a new valid context with that locale and current resolved theme, without transferring translation catalogs or translation ownership

#### Scenario: Unrelated render does not create false authority

- **WHEN** unrelated host state changes without a resolved theme or locale change
- **THEN** the host does not need to issue another context solely because its internal state rendered again; a valid repeated context remains acceptable to the SDK

#### Scenario: Team or frame lifecycle changes

- **WHEN** the selected team, authorized application, or frame target changes or the host unmounts
- **THEN** the previous frame's listener and in-flight work are disposed, and later context updates cannot reach that old frame or bleed its state into the replacement

### Requirement: The context extension has an explicit protocol compatibility gate

The implementation MUST compare the current published SDK and proposed SDK against the current host behavior and extended host behavior before retaining protocol `"1"`. The matrix MUST include optional-theme admission, repeated context delivery, the host's existing legacy-client behavior, initial and later malformed contexts, wrong origin/source/application identity, unsupported protocol, and team/frame lifecycle. Protocol `"1"` SHALL be retained only if all supported old/new combinations remain compatible. If the additive field or repeated context is incompatible with a supported old client, implementation MUST NOT silently change protocol `"1"`; an explicitly reviewed protocol-`"2"` migration MUST preserve protocol-`"1"` host support and version-specific replies before release.

#### Scenario: Current published SDK and current host

- **WHEN** the published SDK is exercised against the pre-extension host behavior
- **THEN** its existing connection, route, request, navigation, open-chat, and disposal behavior remains the compatibility baseline

#### Scenario: Current published SDK and extended host

- **WHEN** the published SDK connects to an extended host that sends optional theme and later contexts
- **THEN** the client remains operational and its existing behaviors remain unchanged even if it does not expose live context updates

#### Scenario: New SDK and current host

- **WHEN** the new SDK connects to a host that sends only the original team, route, and locale context
- **THEN** it remains operational, leaves theme absent, and does not infer FRED theme state

#### Scenario: New SDK and extended host

- **WHEN** the new SDK connects to the extended host across distinct browser origins
- **THEN** it receives the initial resolved theme and locale and later accepted changes while existing route, request, navigation, and disposal behavior remains intact

#### Scenario: Protocol-1 compatibility fails

- **WHEN** any supported old client rejects the optional field or repeated context behavior
- **THEN** protocol-`"1"` retention fails acceptance and an explicit version-`"2"` design retaining version-`"1"` support is reviewed before implementation or release proceeds

### Requirement: The extended SDK is validated as an independent release candidate

Acceptance of the context extension SHALL exercise the actual packed SDK archive and both public entry points in a source-isolated neutral TypeScript consumer and cross-origin browser fixture. Its declaration and executable references, export map, license, asset and dependency boundaries, and package-specific archive checks SHALL retain all existing guarantees. The first SDK release containing the accepted extension MUST use a newly reviewed unused SDK coordinate, matching changelog and immutable candidate evidence, followed by genuine registry verification under the existing independent-release process. Design-token and UI coordinates MUST NOT change solely for this context feature; an existing published SDK version MUST NOT be overwritten.

#### Scenario: Packed SDK exposes live context without framework dependencies

- **WHEN** the actual archive is installed and built in the separately provisioned neutral consumer without checkout or workspace fallback
- **THEN** root and protocol exports provide closed runtime/declaration references for optional theme and `onContext` without React, UI, tokens, or translation dependencies

#### Scenario: Cross-origin browser validates live context

- **WHEN** the installed archive runs in the existing distinct-origin iframe harness with light/dark and locale transitions
- **THEN** the browser observes accepted context updates, rejects wrong origin/source and malformed messages, and preserves existing request/route and frame lifecycle checks

#### Scenario: Release coordinate is chosen after acceptance

- **WHEN** implementation and the compatibility matrix pass and maintainers prepare an SDK release
- **THEN** they verify an unused SDK-only coordinate immediately before versioning and candidate preparation; they do not republish immutable versions or require token/UI versions to change for this feature
