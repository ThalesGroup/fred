## Why

External applications cannot follow FRED's resolved light/dark theme or a locale change while their iframe remains mounted. Protocol `"1"` currently sends team, route, and locale only at connection; the published SDK treats that context as a one-time handshake. The existing [frontend packaging RFC](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md#72-theme-and-locale-synchronization) already identifies a live context extension, and [issue #2712](https://github.com/ThalesGroup/fred/issues/2712) tracks this bounded implementation.

## What Changes

- Add optional `theme: "light" | "dark"` to the single canonical `FredApplicationContext` type and parser. FRED sends its resolved effective theme and locale in the initial context and resends context when either resolved value changes, without changing team/frame isolation or host authority.
- Add `onContext(listener): () => void` to the framework-independent `@fred-oss/iframe-sdk` client. The first valid context still resolves `connect()`; later accepted contexts update `client.context` and notify current context subscribers. Route, request, navigation, open-chat, and disposal contracts remain separate.
- Make protocol compatibility an evidence gate: test current published SDK/current host, current published SDK/extended host, new SDK/current host, and new SDK/extended host. Retain protocol `"1"` only if those tests prove optional-field and repeated-context compatibility; otherwise plan an explicit version-`"2"` migration that keeps version `"1"` supported. No protocol version is selected or changed in this planning change.
- Extend host, protocol, SDK, cross-origin browser, archive, and regression tests. After implementation acceptance, select an unused SDK-only prerelease and use the existing release process; do not bump tokens or UI solely for this feature.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: extend the existing iframe protocol, host-context, SDK-client, and packed-archive requirements with live resolved theme/locale delivery and explicit old/new compatibility gates.

## Impact

Expected implementation surfaces are `apps/frontend/src/rework/features/applications/applicationProtocol.ts`, `apps/frontend/src/rework/components/pages/TeamApplicationHostPage/`, `libs/frontend/iframe-sdk/src/index.ts`, their existing tests, and the current producer/isolated-consumer/cross-origin browser fixtures and documentation. `ApplicationContextProvider.darkMode` is FRED's resolved theme source; `react-i18next` supplies the host locale. The SDK remains generated from the canonical protocol source and must not gain React, FRED state, authentication, or translation dependencies.

Iframe query parameters such as `?theme=dark&locale=fr` are not a live authoritative channel. Deployment-owned `hostOrigin` configuration remains separate. RAGS-specific code, new UI primitives, publication/recovery machinery, registry settings, and FRED/RAGS package adoption are outside this change. The broader RFC stays open for its remaining work.
