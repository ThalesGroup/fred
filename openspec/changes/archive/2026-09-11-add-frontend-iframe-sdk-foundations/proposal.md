## Why

External applications currently have to reproduce FRED's raw `postMessage` integration even
though protocol `"1"` is already implemented and security-sensitive. A small, framework-neutral
archive can make that existing boundary consumable and testable without exposing FRED
authentication or coupling consumers to the FRED checkout.

This is the next bounded slice of
[`FRED-FRONTEND-PACKAGING-RFC.md`](../../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md).
Implementation is tracked by
[ThalesGroup/fred#2614](https://github.com/ThalesGroup/fred/issues/2614).

## What Changes

- Add a non-React `@fred/iframe-sdk` workspace member with a child client at the package root and
  the exact protocol `"1"` wire contract at `@fred/iframe-sdk/protocol`.
- Establish one canonical protocol source shared by the existing FRED host and package generation.
  Preserve the eight serialized message shapes, existing normalizations, request limits, and
  legacy raw-client compatibility; do not maintain parallel host and package definitions.
- Provide explicit connection and context handling, route subscriptions that deliver every
  accepted host route event without sub-path deduplication, navigation and open-chat intents,
  buffered request/reply handling, fixed pending-work limits, deadlines, local abort, and
  deterministic request-ID deduplication, disposal, and late-response behavior.
- Validate the configured HTTP(S) host origin, `window.parent`, incoming message structure,
  protocol version, and the expected application identity before accepting host traffic.
- Keep token refresh, bearer injection, protected-header enforcement, authorized application/team
  resolution, route construction, host request concurrency, and frame/team teardown in FRED.
  The SDK receives no bearer, Keycloak object, host store, upstream address, or backend model.
- Extend the existing producer, exact archive validation, offline neutral consumer, Playwright
  harness, and CI-selection contract for the third package. Inspect runtime and declaration
  references with the TypeScript parser rather than textual patterns, reject malformed or
  non-literal runtime imports, and require runtime references and exports to name exact executable
  packed modules under native ESM rules. Declaration references and `types` exports remain on a
  separate declaration-aware resolution path; preserve every token/UI guarantee.
- Exercise the packed SDK through a real iframe on a loopback child origin distinct from its host
  origin. Provision lockfile-pinned dependencies and Chromium separately from offline install,
  type-check, build, and browser execution.
- Constrain the browser fixture's query-configured destinations to distinct absolute
  `http://127.0.0.1:<port>` origins before either iframe navigates, and keep readonly declaration
  assertions in typecheck-only input outside the browser bundle. These are fixture protections,
  not restrictions on the production SDK's documented HTTP(S) host support.
- Add a direct compatibility integration that loads the actual generated SDK archive and exercises
  the production FRED host handler used by `TeamApplicationHostPage`, while retaining the simulated
  cross-origin browser and raw protocol regression suites.
- Document the shipped client and producer behavior, update the current application-host contract
  references after implementation, and leave the broader RFC open for theme/live-locale changes,
  publication, registry adoption, and external adopter work.
- Exclude protocol changes, streaming or binary transport, remote cancellation, automatic mutation
  retries, UI additions, package publication, FRED registry consumption, and RAGS changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Add the framework-independent iframe SDK's protocol/client,
  compatibility, archive, isolated-consumer, cross-origin browser, and CI-selection requirements
  to the existing frontend package contract.

## Impact

- Canonical host boundary: `apps/frontend/src/rework/features/applications/applicationHost.ts`,
  `applicationPath.ts`, a focused canonical protocol module, and their tests.
- Host compatibility: `TeamApplicationHostPage.tsx` and tests; existing
  `applicationRequest.ts`, application-path, proxy, iframe, token-refresh, and authorization tests
  remain required regression gates. A focused integration fixture will exercise the production
  host handler with the actual packed SDK.
- Producer: `libs/frontend/package.json`, lockfile, Makefile, README, package-input inventory,
  build/pack/archive scripts, and producer tests.
- New package and fixture: `libs/frontend/iframe-sdk/` and a lockfile-pinned neutral TypeScript
  consumer under `libs/frontend/fixtures/`.
- Browser/CI: the existing Playwright harness and `.github/workflows/Check-pending-requests.yml`.
- Fixture hardening: strict loopback-origin parsing and fixed-path URL construction, typecheck-only
  declaration assertions, and browser regressions for invalid configuration before navigation.
- Archive hardening: the SDK validator, build-evidence reference inspection, disposable archive
  mutations, and native ESM import checks.
- Documentation: package READMEs, the durable application-hosting section of
  `CONTROL-PLANE-PRODUCT-CONTRACT.md`, affected frontend guidance, and the existing packaging RFC's
  implementation-status boundary after the slice ships.
- No backend API, application registration, authorization model, deployment, registry, or external
  repository changes are included.
