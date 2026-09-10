## Context

See [proposal.md](proposal.md) for motivation and scope. FRED already hosts external
applications through protocol `"1"`, but the wire contract is embedded in application-host
code and external applications must currently reproduce it. The package producer already
builds and validates `@fred/design-tokens` and `@fred/ui` archives, installs real tarballs into
isolated consumers from a dedicated cache, and runs Playwright against provisioned Chromium.

The current implementation establishes the following constraints:

- `applicationHost.ts` parses four frame messages (`fred:ready`, `fred:navigate`,
  `fred:open-chat`, and `fred:request`) and emits four host messages (`fred:context`,
  `fred:route`, `fred:response`, and `fred:response-error`). It accepts only protocol `"1"`,
  verifies exact source and origin at the host page, and normalizes omitted navigation,
  request-method, header, body, and session fields.
- `applicationPath.ts` rejects absolute, schemed, fragmented, malformed, backslash, null-byte,
  and singly or multiply encoded traversal paths. `applicationRequest.ts` owns bearer injection,
  protected-header rejection, pre-request refresh, one refresh/retry after a 401, and logout only
  when refresh fails. These remain host controls.
- `TeamApplicationHostPage.tsx` has a 15-second ready deadline, a 16-request in-flight bound,
  duplicate-ID refusal, authorized route/chat resolution, and per-frame abort/disposal. Its wire
  response body is always buffered text, including an empty string for bodyless responses.
- The current host responds to repeated ready messages and does not gate every operational raw
  message on a completed handshake. The SDK will not send operational messages before context,
  but this slice will not silently tighten legacy-host behavior.

The RFC is directional rather than proof of current behavior. Its illustrative SDK methods are
not an existing API; its theme/live-locale ideas are deferred; and its opaque-origin discussion
does not match the current HTTP(S), exact-origin host implementation. The configuration guidance
requires HTTPS for production absolute URLs while current code and tests intentionally also
accept HTTP for loopback/local use. The durable application-hosting and authorization contracts,
plus current tests, govern this design where older RFC text differs.

## Goals / Non-Goals

**Goals:**

- Derive the host and the public protocol entry point from one reviewed TypeScript source while
  preserving protocol-`"1"` bytes and legacy raw-client behavior.
- Ship a browser-native, framework-independent child client with explicit admission, bounded
  lifecycle behavior, and Fetch-like buffered responses without exposing host authority.
- Extend the existing exact-archive, offline-consumer, browser, and CI-selection system rather
  than create a second packaging path.
- Make compatibility observable through canonical host regressions, wire-shape fixtures, and a
  packed SDK running in a real cross-origin iframe.

**Non-Goals:**

- Protocol version changes, theme or live-locale extensions, streaming, binary/multipart
  transport, remote cancellation, automatic mutation retries, or opaque/`null` origins.
- Moving authentication, authorization, routing, chat resolution, proxying, concurrency, or token
  refresh into the child.
- Registry publication, converting FRED to registry consumption, UI work, RAGS adoption, or any
  external-repository change.

## Decisions

### 1. Extract one canonical, transport-neutral protocol module from the host

Add `apps/frontend/src/rework/features/applications/applicationProtocol.ts` as the maintained
source for protocol constants, cloneable wire/context types, request methods and limits, pure
host- and frame-message parsers, relative-path validation, and protected-header identification.
The existing host, path, and request modules will import this source and may temporarily re-export
existing names so current FRED callers keep stable imports. Package generation will copy this
allowlisted canonical file into disposable generated input and compile it; developers will not
maintain a package-side copy.

Host-only frame-target parsing, catalog/team/session resolution, route construction, bearer use,
fetching, and React lifecycle code stay in their current application modules. This boundary makes
the wire contract reusable without making internal hosting policy public.

Alternatives considered: maintaining matching protocol files in `apps/frontend` and
`libs/frontend` would permit silent drift; making FRED import an unpublished workspace package
would prematurely perform the registry-adoption migration; generating application source from a
package template would move ownership away from the canonical host. The allowlisted canonical
source plus temporary application re-exports preserves one maintained implementation now and
leaves package consumption for the later publication/adoption slice.

### 2. Expose a small root client and a separate protocol entry point

The package will export only `.` and `./protocol`:

```ts
// @fred/iframe-sdk
createFredApplicationClient(options): FredApplicationClient
FredApplicationClient
FredApplicationClientOptions
FredApplicationRequestInit
FredApplicationClientError
FredApplicationClientErrorCode

interface FredApplicationClient {
  readonly context: FredApplicationContext | null;
  connect(): Promise<FredApplicationContext>;
  onRoute(listener: (route: FredApplicationRoute) => void): () => void;
  navigate(path: string, options?: { replace?: boolean }): void;
  openChat(sessionId?: string | null): void;
  request(path: string, init?: FredApplicationRequestInit): Promise<Response>;
  dispose(): void;
}

interface FredApplicationClientOptions {
  hostOrigin: string;
  applicationId: string;
  connectionTimeoutMs?: number; // default 10,000
  requestTimeoutMs?: number;    // default 30,000
}
```

`FredApplicationRequestInit` supports the six existing methods, `HeadersInit`, a string-or-null
body, `AbortSignal`, and a per-request timeout. The implementation uses browser standards only.
The protocol entry point exposes the existing version, accepted versions, exact message/context
types, methods and limits, pure parsers, path validator, and protected-header helper. Internal
state-machine and generated paths remain blocked by the export map.

Alternatives considered: a single entry point would couple ordinary consumers to low-level wire
details; a class-only constructor complicates test injection and future compatible creation; a
Fetch-shaped unrestricted `RequestInit` would promise body and transport behavior protocol `"1"`
cannot carry.

### 3. Use one admitted-parent lifecycle with bounded connection state

Creation requires an absolute HTTP(S) `hostOrigin` and non-empty expected `applicationId`. The
client captures `window.parent`, rejects a missing usable parent, installs one message listener
before sending ready, and posts only to the configured origin and captured parent. It accepts a
message only from that exact source and origin. A complete matching `fred:context` admits the
parent; malformed contexts, unsupported versions, and application mismatch fail explicitly.

`connect()` is idempotent for a lifecycle: concurrent callers share one promise. Ready is sent
immediately and every 500 milliseconds until admission, disposal, or the configurable connection
deadline (10 seconds by default, deliberately shorter than the host's 15-second frame deadline).
Operational methods require admission. Context is immutable snapshot data; subsequent
`fred:route` messages notify a copy of the current subscriber set. Unsubscribe and disposal are
idempotent.

Wrong-origin/window and unknown messages are ignored because treating ambient browser traffic as
fatal would let unrelated frames deny service. A context from the admitted source/origin with the
wrong application identity is fatal because it demonstrates configuration mismatch.

Alternatives considered: a one-shot ready message retains the current setup race; wildcard origin
or parent discovery weakens admission; accepting operational messages before context recreates the
legacy ambiguity the client is intended to remove.

### 4. Correlate requests locally and reconstruct only the buffered wire transport

The client generates collision-checked IDs with browser crypto, capped at the existing 128
characters. It validates the shared method, 32-header, protected-header, string-body, and relative
path rules before posting. The client permits 16 pending requests, matching the host concurrency
bound, and stores correlation, method, timeout, and abort cleanup per request.

The first structurally valid response for an outstanding ID removes and settles it. Unknown,
duplicate, timed-out, aborted, disposed, and late replies are ignored. Abort and the default
30-second deadline release only local state; protocol `"1"` has no cancel message. Disposal rejects
connection and pending work, clears all timers/subscriptions/listeners, and permanently closes that
client. Errors use stable SDK categories for configuration, connection, lifecycle, capacity,
timeout, application mismatch, validation, and generic host transport failure without inventing a
host-side reason.

`fred:response` resolves a browser `Response`, including non-OK HTTP status. The client supplies a
null body for HEAD and statuses 204, 205, and 304; other bodies remain the host's buffered string.
`fred:response-error` rejects. No automatic retry occurs: the host alone retains its single
token-refresh retry and mutations must not be duplicated by the SDK.

Alternatives considered: transferring streams, binary objects, abort messages, or detailed errors
would change the wire protocol; accepting arbitrary Fetch bodies would fail during structured
clone or imply unsupported serialization; retrying in both layers would duplicate mutations.

### 5. Preserve host authority and prove both compatibility directions

Canonical application tests will retain golden raw protocol-`"1"` inputs and outputs so the
refactored host continues to accept legacy clients. Protocol/client unit tests and the packed
browser fixture prove the new client against current host behavior. The host continues to verify
its own source/origin, application authorization, routes, headers, request capacity, token refresh,
and frame/team lifecycle even if a child bypasses the SDK.

Application identity is required in the initial context. Later route/response messages are trusted
only after admission from the captured source/origin and, for replies, a live request ID; adding an
identity field to each message would be a protocol change. The existing host's acceptance of raw
pre-context operational messages remains covered as legacy behavior, while the SDK itself refuses
to emit them.

Alternatives considered: relying only on SDK validation would weaken hostile-client defenses;
altering every message to carry an application ID or requiring host handshake state would be a
versioned protocol change outside this slice.

### 6. Extend the existing producer with an SDK-specific exact archive contract

Add `iframe-sdk` as a member of the private `libs/frontend` producer workspace. Its publishable
development manifest will use `0.0.0-development`, ESM, `sideEffects: false`, no dependencies or
peers, and an exact file/export inventory for runtime JavaScript, closed declarations, the FRED
license, README, and reviewed build evidence. The workspace root remains `private: true`; that
setting does not describe eventual publication of individual packages.

The generator will use explicit canonical-source and client-source allowlists, create disposable
generated input, compile both entry points, and record source paths/hashes plus build graph/module
externalization evidence. The SDK validator will reuse archive-safety checks and separately verify
exports, executable and declaration closure, metadata, license completeness, dependency absence,
forbidden checkout/workspace references, and exact contents. Mutation tests will prove each class
of rejection while the token and UI validators remain unchanged.

Alternatives considered: hand-copying the protocol violates single ownership; a general bundler
crawl could accidentally package application code; reusing only the UI validator would encode
irrelevant React/CSS/asset assumptions and miss SDK-specific constraints.

### 7. Validate the real tarball in a neutral offline consumer

Add a dedicated TypeScript/browser consumer fixture with its own lockfile. A provisioning command
may use the network to fill a dedicated npm cache with only pinned tooling. Offline validation
creates a fresh OS temporary directory outside FRED, installs the actual packed SDK plus cached
tooling with npm offline mode, then type-checks both entry points and builds the child application.
It must not inspect or resolve FRED's `node_modules`, workspace links, source aliases, React, or
other FRED packages. A missing cache entry fails with the provisioning command; it never falls
back online.

Alternatives considered: running a fixture inside the workspace can conceal missing archive files
and dependencies; permitting install during browser execution makes the offline claim
unrepeatable.

### 8. Exercise host and packed child on distinct loopback origins

Extend the Playwright harness with two HTTP servers on different loopback ports. The child build
imports the installed tarball; the host fixture imports only the packed protocol surface and
models the existing host behavior. Canonical FRED tests remain the evidence for application code,
while cross-origin browser tests cover real `WindowProxy` identity and browser `postMessage`
origins.

The matrix covers handshake retries, context, routes, navigation/open-chat, out-of-order request
correlation, success, HTTP errors, generic transport errors, bodyless responses, malformed and
impersonated messages, capacity, timeout/abort, duplicate and late responses, disposal, and
replacement frame/team lifecycles. Request observation fails on unsuccessful resource responses,
non-loopback destinations, external services, file URLs, or checkout paths. Browser smoke performs
no install or provisioning and reports missing built fixtures or Chromium actionably.

Alternatives considered: same-origin synthetic event tests cannot prove browser origin behavior;
using the live FRED deployment would add authentication and service nondeterminism to a package
contract test.

### 9. Select exact inputs and update durable documentation

The frontend-package CI selector will include the SDK workspace, validator, fixtures, browser
harness, producer metadata/lockfile, shared archive utilities, and every canonical protocol/path
source consumed by generation. Canonical protocol/path changes select both package validation and
the frontend application gates; host/request/page/proxy/auth-regression inputs continue to select
the relevant frontend compatibility gates. Selection tests will include positive cases for every
new input class and negative cases for unrelated application files.

Implementation documentation will add the SDK consumer README, extend the producer README,
identify the canonical contract in the control-plane product contract and frontend guidance, and
update only the existing packaging RFC's implementation-status and suggested-location statements
that become stale. The broader RFC remains open.

## Risks / Trade-offs

- **[A canonical source under the application is packaged externally]** → Keep it transport-only,
  enforce an explicit graph, and validate the host and archive derive from its recorded hash.
- **[The temporary host re-export bridge can outlive its purpose]** → Document it as prepublication
  compatibility and schedule removal only with the later registry-adoption change.
- **[Client and host both use a 16-request bound]** → The client fails the seventeenth request
  locally, while the host retains its independent bound against raw or hostile clients.
- **[Local timeout/abort does not stop host work]** → Document it, discard late replies, and do not
  add an unversioned cancel message.
- **[HTTP is accepted by the SDK]** → Limit it to ordinary HTTP(S) origins; use HTTP only for
  loopback tests and retain the production HTTPS configuration requirement.
- **[A host fixture can drift from FRED behavior]** → Share the packed protocol surface, preserve
  raw-wire golden tests, and run the actual host/request/path/proxy regression suites in the same
  change.
- **[Browser APIs limit non-browser or opaque-origin use]** → State browser-window and HTTP(S)
  requirements explicitly; worker, server, sandboxed-null-origin, and opaque-origin support need a
  future protocol/hosting decision.

## Migration Plan

1. Freeze protocol-`"1"` golden vectors and caller imports, then extract the canonical protocol
   primitives with compatibility re-exports and run existing host/request/path tests.
2. Implement and unit-test the child client against the canonical protocol without changing host
   authority or serialized shapes.
3. Generate, pack, validate, and consume the SDK archive; retain all token/UI checks.
4. Add distinct-origin browser evidence and exact CI selection.
5. Update durable documentation and complete frontend/package regression and independent review.

Rollback removes the new workspace member, fixture, producer/CI entries, and documentation while
restoring host imports through the compatibility re-exports. Because the slice does not publish,
adopt the package in FRED, or change protocol bytes, rollback does not require a registry,
deployment, or consumer migration.
