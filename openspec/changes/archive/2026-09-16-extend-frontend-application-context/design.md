## Context

See [proposal.md](proposal.md) and the [delta specification](specs/frontend-package-archives/spec.md). The [RFC §7.2](../../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md#72-theme-and-locale-synchronization) describes the intended extension; the current code establishes its starting point. `applicationProtocol.ts` is the sole maintained wire/type/parser source and the SDK producer copies it into generated input. Its context parser currently returns team, route, and locale and drops unknown fields. `TeamApplicationHostPage.tsx` sends context only in response to `fred:ready`; it already keeps route and locale in a live ref and remounts the frame on team/application/target change. The SDK resolves `connect()` from the first valid context but ignores all later contexts. Its route subscribers use snapshot iteration, catch each listener exception, and report it without stopping delivery.

`ApplicationContextProvider.tsx` owns `themeMode` and computes `darkMode` from the selected mode and `prefers-color-scheme`; `App.tsx` applies the result to the document. The host page already reads `i18n.resolvedLanguage ?? i18n.language ?? "en"`. Therefore the host can send `darkMode ? "dark" : "light"` and the resolved locale without reading DOM attributes or handing provider/i18n state to the child. The [control-plane application contract §46](../../../../docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) still describes the shipped team/route/locale context; implementation documentation will update it only after behavior is verified. Current main OpenSpec still says this context behavior is deferred and uses old `@fred/iframe-sdk` wording in some earlier requirements; this delta replaces the affected behavior with the real `@fred-oss/iframe-sdk` coordinate without synchronizing unrelated release changes.

## Goals / Non-Goals

**Goals:**

- Keep one canonical protocol source and one `fred:context` channel for initial and live resolved values.
- Preserve host-owned authorization, source/origin admission, request/route controls, and old-frame disposal.
- Prove whether optional theme and repeated context are compatible with supported protocol-`"1"` clients before deciding the wire version.
- Validate the built SDK archive and framework-free consumer, not just canonical source tests.

**Non-Goals:**

- Consumer translation state or catalogs, SDK/UI i18n dependencies, FRED/RAGS adoption, RAGS-specific values, iframe URL synchronization, DOM/storage inspection, or a second messaging bus.
- Changing request transport, proxy/authentication, route semantics, token/UI packages, or release/publication machinery.
- Choosing an SDK prerelease number or performing publication in this planning change.

## Decisions

### 1. Extend the canonical parser and type, not a package-side copy

Add optional readonly `theme?: "light" | "dark"` to `FredApplicationContext` in `apps/frontend/src/rework/features/applications/applicationProtocol.ts`. `parseContext` accepts absence for old hosts, preserves a valid present theme, and rejects a present invalid value; it continues to return only reviewed cloneable fields. The existing `libs/frontend/scripts/build-iframe-sdk.mjs` allowlist and `./protocol` export remain the generation path. Protocol version remains `"1"` while the compatibility gate runs. This avoids duplicate definitions and distinguishes optional wire compatibility from a claim that every old host supplies a theme.

Alternative rejected: add theme in an SDK-local interface or infer it from the parent's DOM; either breaks the single-source boundary or gives a cross-origin child impossible/unauthorized knowledge.

### 2. Publish current resolved values from the existing host frame lifecycle

In `ApplicationFrame`, read `darkMode` from `ApplicationContext` and derive the literal effective theme. Keep the current `react-i18next` resolved-locale choice. A shared host-side context construction/post path serves the initial ready reply and later value changes, using the current team/route ref so route data does not become stale. Record the theme/locale pair sent by the ready reply; a post-ready effect keyed by resolved theme and locale sends only a changed pair to the current ready frame, avoiding an accidental duplicate just because status became ready. It must not cause a new frame, replay `fred:ready`, echo `fred:route`, or alter the host listener/request effect's dependency lifecycle. Frame replacement and cleanup still terminate the old listener and abort its in-flight requests. If a theme/locale change races ready, the initial message must contain the latest resolved values; if it occurs after ready, the same frame receives an update.

Alternative rejected: query `document.documentElement.dataset.theme` or encode `theme`/`locale` in the iframe URL. The provider is the value owner; the DOM attribute is its presentation effect, and URL parameters would be stale after a live change. Deployment-owned `hostOrigin` remains independent configuration.

### 3. Treat subsequent context as admitted events, separate from route events

Extend the SDK's existing parent/origin-gated message handler so a first valid matching context retains its one-shot connection behavior, while later valid matching contexts replace the frozen `client.context` snapshot and notify a separate context subscriber set. `onContext` follows `onRoute`'s connected-state registration pattern and returns an idempotent unsubscribe. It does not replay the initial snapshot; consumers read `client.context` or the `connect()` result for initial state. Every accepted later message is delivered, including equal-valued repeats, because it is a host event rather than a value-deduplicated store update. Snapshot subscriber iteration and per-listener `try/catch` with `globalThis.reportError?.(error)` match the route path. An invalid or misattributed later context is ignored without losing the last valid snapshot or interrupting pending requests. Disposal clears both subscriber sets.

This SDK only passes context data; a consumer chooses how its own UI root and translations react. When `theme` is absent, the SDK leaves it absent, and the consumer chooses a local/system/default fallback. It never reads the parent document or fabricates FRED theme truth. Route subscribers are not invoked by a context update, and business-state reset is not an SDK side effect.

Alternative rejected: merge context and route subscriptions or invoke `onContext` immediately on registration. Either obscures whether a later host message occurred and complicates existing route-event semantics; initial state already has `connect()` and `client.context`.

### 4. Make compatibility a measured stop/go decision

Before a version decision, run the following matrix with recorded exact inputs:

| SDK | Host | Evidence expected |
| --- | --- | --- |
| Published `@fred-oss/iframe-sdk@0.1.0-alpha.1` | Pre-extension host at this branch's baseline commit `4a69a0229163cd354cdf36f62ca7e213aeaeebaf` | Existing handshake, route/request, and lifecycle behavior |
| Published SDK | Extended host | Optional theme and later `fred:context` do not break supported old-client operation; old client need not expose updates |
| New packed SDK | Pre-extension host | Team/route/locale connect successfully with absent theme and no fabricated fallback |
| New packed SDK | Extended host | Initial light/dark, both theme directions, locale transition, identical repeats, security rejects, and team/frame lifecycle |

Provision the exact published archive and any historical-host source/dependencies in a distinct network-capable phase, pin their identity/integrity and provenance to independently reviewed release evidence, and fail if the baseline cannot be obtained. A disposable checkout of the pinned host commit, not a second maintained production host implementation, supplies the old-host side; application dependencies remain those of that host checkout. The new SDK side uses an actual generated/validated tarball installed in the existing source-isolated neutral consumer. Existing raw-client host regressions are complementary, not a substitute for the published SDK combinations. The cross-origin harness uses distinct host/child/attacker origins and an explicitly configured `hostOrigin`, not theme/locale URL inputs.

Record matrix results before retaining protocol `"1"`. If an old supported client rejects the optional field or repeated context, stop this implementation path, revise the change's protocol requirements/design for explicit version-`"2"` negotiation, retain a version-`"1"` host reply path, and obtain review before further implementation. Neither the RFC nor the presence of an optional TypeScript property proves wire compatibility. No automatic constant bump is authorized by this plan.

### 5. Preserve package and release boundaries

Extend `iframe-sdk-client.test.mjs`, canonical protocol/host tests, the installed `iframe-sdk-consumer` fixture, and `browser-smoke.mjs`. Verify root and `./protocol` declarations, exports, executable/declaration closure, license, no React/UI/token/i18n dependency, and existing negative archive cases with `validate-iframe-sdk-archive.mjs`. Keep producer dependency/Chromium provisioning separate from offline tarball installation, type-check/build, browser execution, and production-host integration. Continue existing `applicationRequest`, `applicationPath`, proxy/authentication, token, and UI regressions and extend `package-inputs.mjs`/CI-selection tests for the theme owner, locale, host, SDK, fixture, and validation inputs newly consumed by this feature.

After code and compatibility acceptance, review an unused SDK-only prerelease coordinate immediately before updating its manifest/changelog and creating immutable release-candidate evidence. Run the established release checks; genuine publication/registry verification is a later authorized operation, never inferred from local fixtures. Tokens and UI do not need versions solely for this change; an immutable published SDK version is never overwritten. The still-active independent-release OpenSpec change owns general selection, evidence, and publishing mechanics, so this change does not duplicate them.

## Risks / Trade-offs

- **An older SDK may reject repeated or enriched context** → Run the four-way matrix with the actual published archive; fail the protocol-`"1"` gate and design explicit version-`"2"` coexistence if needed.
- **A host update may use stale route/locale or send into a replaced frame** → Reuse current context refs and frame/status guards; test ready races, theme/locale changes, team switch, and cleanup.
- **Listener exceptions could interrupt delivery or corrupt latest state** → Commit validated snapshot before isolated callbacks, then report each exception using the existing route policy.
- **Historical-host source or published SDK evidence may be unavailable** → Treat the compatibility gate as blocked, not satisfied by a hand-written mock or current-source substitution.
- **A consumer may mistake absent theme for a host-selected default** → Document absence as absence and leave fallback to the consumer, including the no-parent-DOM constraint.

## Migration Plan

1. Add canonical optional-theme parsing and host resolved-context emission with legacy host/protocol regressions; do not change the protocol constant.
2. Extend the SDK client, unit tests, installed neutral consumer, cross-origin browser harness, and package/CI validation; retain all existing request and host guarantees.
3. Execute and record the complete old/new matrix. If protocol `"1"` fails, stop and obtain a reviewed explicit version-`"2"` migration that keeps version-`"1"` support; do not ship a silent compatibility break.
4. After implementation acceptance, update SDK documentation and the compact application integration contract, review an unused SDK prerelease, and prepare/validate immutable SDK-only release evidence through the existing tooling. Publication and adopter upgrades require separate authorization. A consumer can roll back to the prior SDK version while the host continues to serve the prior protocol.
