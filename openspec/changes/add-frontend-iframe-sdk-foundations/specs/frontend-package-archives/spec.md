## ADDED Requirements

### Requirement: The iframe SDK exposes a framework-independent public contract

The `@fred/iframe-sdk` archive SHALL expose its child client from `.` and the shared
protocol `"1"` wire contract from `./protocol` as ESM JavaScript and closed TypeScript
declarations. It MUST NOT depend on React, React DOM, `@fred/ui`,
`@fred/design-tokens`, FRED application state, routing libraries, Keycloak, backend
models, or consumer-specific code. Undocumented deep imports MUST remain blocked.

#### Scenario: A neutral TypeScript consumer imports both entry points

- **WHEN** an application with no framework dependency imports the documented client
  API and protocol types from the packed archive
- **THEN** type checking and production bundling succeed without React, another FRED
  package, a deep import, or access to FRED source

#### Scenario: A consumer requests an internal module

- **WHEN** a consumer attempts to import a generated or internal SDK module
- **THEN** the package export map prevents that module from becoming public API

### Requirement: One authoritative source defines protocol 1

FRED and the generated package SHALL consume one maintained protocol source for the
existing `fred:ready`, `fred:context`, `fred:route`, `fred:navigate`, `fred:open-chat`,
`fred:request`, `fred:response`, and `fred:response-error` messages. The serialized
field names, required values, and existing default normalization MUST remain compatible
with protocol `"1"`. Package generation MUST NOT introduce a second maintained wire
definition.

The protocol entry point SHALL expose the version, message and context types, request
methods and limits, pure message parsers, protected-header predicate, and relative-path
validator needed by the host and child. Host-only catalog, frame-target, route-target,
session-resolution, bearer, and fetch implementations MUST remain outside it.

#### Scenario: The updated host receives a legacy client message

- **WHEN** a raw protocol-`"1"` client sends any currently supported frame-to-host
  serialized shape
- **THEN** the host preserves its current parsing, defaults, routing, request, and error
  behavior

#### Scenario: The new SDK connects to the protocol-1 host

- **WHEN** the packed SDK sends protocol-`"1"` messages to the existing host behavior
- **THEN** the host accepts them without a protocol extension or compatibility adapter

#### Scenario: Generated protocol output diverges

- **WHEN** the host and packed protocol entry point are no longer derived from the same
  canonical source and reviewed build graph
- **THEN** generation or compatibility validation fails before the archive is accepted

### Requirement: Connection admission is explicit and bounded

The client SHALL require an explicit HTTP(S) host origin and expected application ID.
It SHALL install its listener before sending `fred:ready`, post only to that exact
origin and `window.parent`, and accept messages only when `event.origin` equals the
configured origin and `event.source` equals `window.parent`. A valid initial
`fred:context` MUST carry protocol version `"1"`, the expected application ID, and the
complete cloneable team, route, and locale context before the client becomes connected.

`connect()` SHALL send `fred:ready` immediately and retry at a fixed bounded cadence
until it connects or reaches a default 10-second connection deadline. Concurrent calls
SHALL share the same connection lifecycle. A missing parent, malformed context,
unsupported protocol, application-ID mismatch, deadline, or disposal MUST fail
actionably rather than becoming a silent connection.

#### Scenario: A configured child completes the handshake

- **WHEN** the expected parent answers a ready announcement from the configured origin
  with a valid matching context
- **THEN** connection resolves once with that context and handshake retries stop

#### Scenario: A ready announcement races host setup

- **WHEN** the first ready announcement is not observed but the host becomes available
  before the connection deadline
- **THEN** a bounded retry permits connection without creating a second client lifecycle

#### Scenario: A message comes from the wrong source or origin

- **WHEN** a structurally valid host message comes from another window or a different
  origin
- **THEN** the client ignores it without connecting, navigating, or settling a request

#### Scenario: Context names another application

- **WHEN** the configured parent sends a context whose application ID differs from the
  client's expected identity
- **THEN** connection fails with an application-mismatch error and no operational host
  message is accepted

#### Scenario: The host never completes the handshake

- **WHEN** no valid matching context arrives within the connection deadline
- **THEN** connection rejects, retries and timers stop, and operational methods remain
  unavailable

### Requirement: Context, route, and navigation APIs preserve host ownership

The connected client SHALL expose the accepted initial context and route-event
subscriptions. It SHALL deliver each accepted `fred:route` message exactly once to each
subscriber that is current when the message is handled. It MUST NOT deduplicate accepted
route messages solely because their `subPath` equals a previously delivered value. It
SHALL send only relative `fred:navigate` intents with explicit
replace semantics and `fred:open-chat` with a string session candidate or `null`.
Relative path validation MUST reject absolute, schemed, fragmented, malformed,
backslash, and single- or multiply-encoded traversal paths before posting while the
host remains authoritative.

The SDK MUST NOT inspect or mutate the parent DOM, select a FRED route outside the
application subtree, resolve a chat destination, infer team identity, or add theme or
live-locale context behavior in this slice.

#### Scenario: The host changes the application route

- **WHEN** a connected client receives a valid `fred:route` message from its accepted
  parent and origin
- **THEN** every current route subscriber receives the host-owned sub-path once

#### Scenario: Navigation returns to a previously delivered route

- **WHEN** the host sends route A, the child requests navigation to B, and the host later
  sends route A again
- **THEN** every subscriber current for each host message observes A and then A again,
  with neither accepted route event suppressed by sub-path deduplication

#### Scenario: A consumer requests application navigation

- **WHEN** a connected consumer supplies a valid relative path and replace choice
- **THEN** the client sends the existing normalized `fred:navigate` shape without
  choosing the resulting FRED route

#### Scenario: A consumer opens chat with no trusted destination

- **WHEN** a consumer calls open-chat with an optional session candidate
- **THEN** the client sends only that candidate and the host retains all destination and
  authorization decisions

#### Scenario: A path attempts to escape

- **WHEN** a consumer supplies an absolute, schemed, fragmented, malformed, or
  traversing path to navigation or request
- **THEN** the client rejects it locally and sends no message

### Requirement: Request correlation, limits, cancellation, and disposal are deterministic

The client SHALL generate unique protocol-`"1"` request IDs no longer than 128
characters, permit only `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE`, serialize
at most 32 ordinary string headers, and allow no more than 16 pending requests. It MUST
reject protected headers case-insensitively before posting. Requests issued before
connection or beyond the pending bound MUST fail locally.

Replies SHALL correlate by request ID and may arrive out of order. The first valid
reply SHALL settle and remove its pending request; duplicate, unknown, canceled, timed
out, disposed, or otherwise late replies MUST be ignored. Requests SHALL have a
default 30-second local deadline and accept caller `AbortSignal` cancellation. Timeout
or abort releases local state but MUST NOT claim to cancel host fetch or remote work and
MUST NOT automatically retry a mutation.

`dispose()` SHALL be idempotent, remove listeners, stop connection/request timers,
reject unsettled work, clear subscribers, and make subsequent operations fail. A new
frame lifecycle SHALL require a new client.

#### Scenario: Responses arrive out of order

- **WHEN** two accepted requests receive valid replies in the reverse order
- **THEN** each promise settles exactly once with the reply carrying its generated ID

#### Scenario: Pending capacity is exhausted

- **WHEN** 16 requests remain pending and a consumer attempts another request
- **THEN** the additional request fails locally without sending a seventeenth message

#### Scenario: A request times out or is aborted

- **WHEN** its local deadline expires or its caller signal aborts before a reply
- **THEN** the promise rejects predictably, its pending slot is released, and no remote
  cancellation or automatic retry is claimed

#### Scenario: A duplicate or late reply arrives

- **WHEN** a reply arrives after its request settled, timed out, was canceled, or the
  client was disposed
- **THEN** the client ignores it without settling another request or restoring state

#### Scenario: The client is disposed with pending work

- **WHEN** disposal occurs during connection or one or more requests
- **THEN** every unsettled promise rejects, all local resources are released, and a
  later message from the old frame lifecycle has no effect

### Requirement: The request API describes the buffered protocol accurately

The public request API SHALL accept only the protocol's string-or-null body and SHALL
reconstruct a browser `Response` from a successful `fred:response`. HTTP error statuses
including 401, 403, and 5xx MUST resolve as Responses whose status and headers remain
inspectable; `fred:response-error` and local transport failures MUST reject separately.
HEAD and status 204, 205, or 304 responses MUST be reconstructed without a body so
bodyless replies do not throw during construction.

Documentation MUST identify this as buffered text/JSON transport rather than full Fetch
equivalence. It MUST NOT promise binary bodies, multipart uploads, response streaming,
SSE, remote cancellation, detailed host transport reasons, or automatic retry.

#### Scenario: A successful JSON response arrives

- **WHEN** the host returns a successful status, headers, and buffered JSON text
- **THEN** the resolved Response exposes the same status and headers and its text or JSON
  reader consumes the buffered body

#### Scenario: The application service returns an HTTP error

- **WHEN** the host returns 401, 403, or a 5xx `fred:response`
- **THEN** the request resolves with that non-OK Response rather than becoming an SDK
  transport exception

#### Scenario: The host reports a transport failure

- **WHEN** the host sends `fred:response-error` for a pending request
- **THEN** the request rejects with a generic transport error that does not invent or
  expose a host-side reason

#### Scenario: A bodyless response arrives

- **WHEN** a HEAD request or 204, 205, or 304 response carries the host's buffered empty
  string
- **THEN** the SDK constructs a valid bodyless Response while preserving status and
  headers

### Requirement: FRED remains the authority for hosting and authenticated requests

The extraction SHALL preserve FRED's authorized application lookup, configured frame
target, exact source/origin checks, 15-second host handshake deadline, 16-request host
concurrency bound, duplicate-ID refusal, route and open-chat resolution, team/frame
teardown, protected-header enforcement, bearer injection, pre-request refresh, single
401 retry, and logout-only-on-refresh-failure behavior. No bearer, Keycloak object,
host state, service upstream, or authorization result MAY enter SDK context or messages.

#### Scenario: A frame or team lifecycle changes

- **WHEN** the hosted application, frame target, or selected team is replaced or the
  host unmounts
- **THEN** the old host listener is removed, its in-flight fetches are aborted, and old
  frame messages or replies cannot affect the new lifecycle

#### Scenario: A protected header bypasses local validation

- **WHEN** a legacy or hostile client sends a protected request header directly
- **THEN** the host still rejects it without forwarding the caller's value

#### Scenario: The application service returns 401

- **WHEN** the host request adapter receives an application-service 401
- **THEN** FRED preserves its one refresh/retry policy and logs out only when refresh
  itself fails, independently of SDK behavior

#### Scenario: The packed SDK exercises the production host handler

- **WHEN** the actual generated SDK tarball connects to the production message handler used by
  FRED's host page
- **THEN** ready/context, route delivery, navigation, open-chat, request correlation, HTTP and
  transport outcomes, pending limits, and stale frame/team teardown work without a protocol
  adapter or loss of host authority

#### Scenario: Host routing returns to a prior route through the packed SDK

- **WHEN** the production host sends route A, the packed SDK sends child navigation to B, and the
  production host later sends route A
- **THEN** the SDK delivers both accepted A events to current subscribers while request responses
  remain deduplicated by request ID

### Requirement: The iframe SDK archive is complete and independently consumable

Acceptance of the actual `npm pack` SDK tarball SHALL validate its exact `.` and
`./protocol` export map, declarations, executable-module closure, file inventory,
metadata, complete FRED license, dependency absence, canonical-source/build evidence,
and freedom from checkout paths, aliases, links, local dependency protocols, bundled
Node code, and unrelated FRED package or application code. Runtime imports and runtime
export conditions MUST resolve to executable packed modules. Declaration references and
`types` export conditions MAY resolve to valid packed `.d.ts` files and MUST be checked
with declaration-aware resolution independently of runtime resolution. A declaration-only
target MUST NOT satisfy a runtime reference. Existing design-token and UI positive and
negative archive guarantees MUST continue unchanged.

Reference inspection SHALL use the TypeScript compiler API to parse JavaScript and declaration
syntax and inspect static imports, re-exports, dynamic imports, declaration import types, and
applicable reference directives. Comments MUST NOT hide a reference. Literal strings and
no-substitution template literals MUST be inspected. A computed runtime import or malformed module
syntax MUST fail validation. Build-graph evidence SHALL use the same syntax-aware reference
inspection rather than a less complete textual scan.

Every packed executable module SHALL also pass a parse-only native ESM grammar check without being
imported or executed. The check MUST reject grammar-invalid JavaScript that a permissive TypeScript
AST can still represent, including top-level `return` and TypeScript-only annotations in `.js`.

Runtime relative references SHALL resolve exactly as written to executable packed JavaScript.
Validation MUST NOT infer an omitted extension or fall back from a directory to `index.js` because
native ESM consumption does not perform those substitutions. Declaration resolution SHALL remain
separate and declaration-aware.

A lockfile-pinned neutral JavaScript/TypeScript consumer SHALL install the actual SDK
tarball in a fresh OS temporary directory outside FRED, type-check both public entry
points, and produce a browser build without React or any other FRED package.

#### Scenario: The actual SDK archive is validated

- **WHEN** the SDK workspace member is generated, packed, and checked
- **THEN** every runtime reference resolves to executable packed JavaScript, every
  declaration reference resolves to a valid packed declaration, and the package has no
  undeclared or framework dependency

#### Scenario: Runtime references resolve through executable modules

- **WHEN** a valid runtime entry point or executable packed module imports or exports
  another runtime module
- **THEN** archive validation resolves the reference through executable files contained
  in the exact packed archive

#### Scenario: Comments surround a static module reference

- **WHEN** a runtime or declaration import places comments between its syntax tokens and its
  literal module specifier
- **THEN** syntax-aware validation still inspects and resolves that reference through the
  applicable runtime or declaration path

#### Scenario: A dynamic import uses a literal template

- **WHEN** runtime JavaScript dynamically imports a no-substitution template literal
- **THEN** archive validation resolves its exact target as an executable packed module

#### Scenario: A runtime import is computed

- **WHEN** runtime JavaScript calls `import()` with an identifier, expression, or interpolated
  template rather than a statically reviewable module literal
- **THEN** SDK archive validation fails instead of accepting an unknown runtime dependency

#### Scenario: Packed module syntax is malformed

- **WHEN** an executable or declaration module cannot be parsed without syntax diagnostics
- **THEN** SDK archive validation fails before accepting its reference graph

#### Scenario: A runtime module is not valid native ESM grammar

- **WHEN** a packed executable contains top-level `return`, TypeScript-only annotations, or another
  construct that the TypeScript AST accepts but native ESM grammar rejects
- **THEN** parse-only native validation rejects the archive without executing the module

#### Scenario: A runtime import omits its executable extension

- **WHEN** runtime JavaScript imports `./protocol` while only `./protocol.js` is packed
- **THEN** archive validation fails and a native ESM loading check confirms the entry point is not
  consumable as written

#### Scenario: A runtime import names a packed directory

- **WHEN** runtime JavaScript names a directory whose `index.js` could be found only by fallback
- **THEN** archive validation fails rather than treating the directory as an executable target

#### Scenario: A runtime reference has only a declaration target

- **WHEN** a runtime import or runtime export condition resolves only to a packed `.d.ts`
  file or similarly named declaration
- **THEN** SDK archive validation fails even though TypeScript declaration resolution
  could find that target

#### Scenario: Declaration references resolve through packed declarations

- **WHEN** a valid declaration import, reference, or `types` export condition names a
  packed declaration target
- **THEN** archive validation resolves it through the applicable `.d.ts` file without
  requiring that type-only target to be executable

#### Scenario: Declaration import types remain declaration-aware

- **WHEN** a declaration contains a commented or ordinary `import("./types.js").Name` reference
- **THEN** syntax-aware validation resolves it using the packed declaration graph without applying
  runtime executable-target rules

#### Scenario: A declaration reference is missing or invalid

- **WHEN** a declaration import, reference, or `types` export condition has no valid
  packed `.d.ts` target
- **THEN** SDK archive validation fails even if similarly named executable JavaScript is
  present

#### Scenario: An archive reference is missing or escapes

- **WHEN** JavaScript, declarations, or exports reference a missing, aliased, absolute,
  checkout-relative, undeclared, or outside-package target
- **THEN** SDK archive validation fails before consumption

#### Scenario: The tarball is consumed outside FRED

- **WHEN** the neutral consumer installs the SDK tarball and pinned tooling offline,
  imports both entry points, type-checks, and builds
- **THEN** it succeeds without FRED source, FRED dependencies, a workspace or local
  package link, or React

#### Scenario: Existing package validation runs with the SDK

- **WHEN** the producer's complete suite runs after adding the SDK member
- **THEN** every existing token and UI generation, archive mutation, isolated-consumer,
  CSS, asset, license, peer, and browser assertion retains its meaning

### Requirement: Provisioning is separate from offline SDK validation

Dependency provisioning MAY download only lockfile-pinned neutral-consumer dependencies
into a dedicated cache, and browser provisioning MAY install the pinned browser before
validation. Offline consumer validation MAY install the actual SDK tarball and pinned
dependencies from that cache, but MUST NOT fetch from the network, resolve FRED's
installed dependency tree, or bootstrap a missing browser. Browser smoke execution
MUST perform no dependency installation or browser provisioning.

#### Scenario: Offline prerequisites are available

- **WHEN** the dedicated cache and pinned browser were provisioned separately
- **THEN** fresh consumer installation, type checking, production build, and browser
  smoke complete without an external network request

#### Scenario: A cache or browser prerequisite is missing

- **WHEN** offline validation starts without a required cached package or browser
- **THEN** it fails with the applicable provisioning command and does not fall back to
  the network or FRED dependencies

### Requirement: Browser evidence uses a real cross-origin iframe

The packed SDK SHALL be exercised in a real iframe whose loopback child origin differs
from the loopback host origin. Browser checks SHALL cover handshake and context,
host-to-child route events, child navigation and open-chat intents, request/reply
correlation, successful and HTTP-error Responses, transport failures, bodyless
Responses, malformed messages, wrong origins and windows, capacity, deadlines,
disposal, late responses, and host frame/team lifecycle behavior. Every resource
response MUST succeed locally, and non-loopback, `file:`, external-service, and FRED
checkout requests MUST fail validation.

#### Scenario: Distinct origins complete the protocol lifecycle

- **WHEN** the isolated child runs in an iframe on a different loopback origin from its
  host fixture
- **THEN** the packed client connects and exercises context, routes, intents, and
  buffered requests using only exact-origin `postMessage`

#### Scenario: Another window impersonates the parent or child

- **WHEN** a sibling, popup, stale frame, or wrong-origin document sends an otherwise
  valid protocol message
- **THEN** the receiving client or host ignores it because both source and origin do not
  match the configured lifecycle

#### Scenario: Browser resources leave the isolated fixture

- **WHEN** either host or child requests a non-loopback resource, a FRED checkout path,
  a file URL, or an unsuccessful resource
- **THEN** browser validation fails rather than accepting partial protocol evidence

### Requirement: The iframe SDK remains application-agnostic

The SDK, protocol source, fixtures, and archive SHALL contain no RAGS identity, consumer
route, business model, service endpoint, token, registry assumption, or
application-specific branch. Consumer values SHALL enter only through documented
configuration, context, paths, bodies, headers, and handlers. This slice MUST NOT
change protocol version `"1"`, application registration, authorization policy, or
deployment ownership.

#### Scenario: A different external application uses the SDK

- **WHEN** a neutral consumer supplies a different valid application ID, host origin,
  route, and ordinary request data
- **THEN** the same packed client operates without package or host changes specific to
  that consumer

## MODIFIED Requirements

### Requirement: CI selection covers every package-validation input

Pull-request validation SHALL select the frontend-package job when the producer
workspace; a consumed canonical component, type, stylesheet, protocol source, or path
validator; the FRED frontend React manifest or lockfile baseline; a packaged Geist or
Material Symbols asset; an applicable license or notice input; an SDK compatibility or
isolated-consumer fixture; or relevant validation orchestration changes. It MAY skip
that job for application changes that affect neither package generation nor package/host
compatibility validation. Existing frontend selection MUST continue to run the FRED
host, request, path, and proxy regressions when their application inputs change.

#### Scenario: The producer workspace changes

- **WHEN** a pull request changes a file in the frontend package producer workspace
- **THEN** CI selects the frontend-package validation job

#### Scenario: Consumed canonical CSS changes

- **WHEN** a pull request changes a canonical FRED stylesheet consumed by token, font,
  shared-base, or component-style generation
- **THEN** CI selects the frontend-package validation job

#### Scenario: A consumed component or type changes

- **WHEN** a pull request changes a canonical component, shared prop or visual type, or
  Sass support file in the UI package allowlist
- **THEN** CI selects the frontend-package validation job

#### Scenario: A canonical protocol or path rule changes

- **WHEN** a pull request changes the maintained protocol source or relative-path rules
  consumed by the SDK and host compatibility checks
- **THEN** CI selects both frontend-package validation and the applicable FRED frontend
  regression checks

#### Scenario: A host compatibility input changes

- **WHEN** a pull request changes the application host page, request adapter, frame/path
  integration, or their compatibility tests
- **THEN** CI selects the FRED frontend regression checks and every declared SDK/host
  compatibility gate affected by that input

#### Scenario: The tested React baseline changes

- **WHEN** a pull request changes the FRED frontend manifest or lockfile entries that
  establish the UI package's tested React or React DOM baseline
- **THEN** CI selects the frontend-package validation job

#### Scenario: A packaged Geist asset changes

- **WHEN** a pull request changes either canonical Geist font binary packaged by the
  design-token member
- **THEN** CI selects the frontend-package validation job

#### Scenario: The packaged Material Symbols asset changes

- **WHEN** a pull request changes the canonical Material Symbols Outlined binary used by
  the UI member
- **THEN** CI selects the frontend-package validation job

#### Scenario: An applicable license input changes

- **WHEN** a pull request changes a license, provenance record, glyph inventory, or
  notice input applicable to a generated archive
- **THEN** CI selects the frontend-package validation job

#### Scenario: Validation orchestration changes

- **WHEN** a pull request changes a root command, workflow, setup action, build
  configuration, fixture lockfile, or validation script that controls the
  frontend-package or host-compatibility gates
- **THEN** CI selects the affected validation jobs

#### Scenario: An unrelated application file changes

- **WHEN** a pull request changes only application files that are not consumed by or
  responsible for frontend-package or SDK/host compatibility validation
- **THEN** CI may skip the frontend-package job while retaining normal application
  validation
