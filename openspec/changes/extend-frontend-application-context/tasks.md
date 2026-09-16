## 1. Freeze compatibility inputs and canonical protocol behavior

- [x] 1.1 Record the pre-extension host baseline at `4a69a0229163cd354cdf36f62ca7e213aeaeebaf` and provision the exact published `@fred-oss/iframe-sdk@0.1.0-alpha.1` archive with independently checked integrity/provenance; verify a disposable baseline host/SDK test can run without substituting current source or a mock.
- [x] 1.2 Add optional readonly `theme?: "light" | "dark"` to `FredApplicationContext` and its canonical `parseContext` in `applicationProtocol.ts`; verify `applicationProtocol.test.ts` accepts missing/light/dark, preserves valid theme, rejects `"system"`, null and other invalid present values, and retains protocol `"1"` golden wire shapes and request limits.
- [x] 1.3 Rebuild the SDK protocol export from the canonical allowlist and verify `build-iframe-sdk.test.mjs` demonstrates deterministic output hashes/evidence across repeated builds of the updated canonical inputs and preserves the expected closed source/module graph, with no manually maintained second protocol type or version bump.

## 2. Host resolved context and lifecycle

- [x] 2.1 In `TeamApplicationHostPage.tsx`, derive `"light"`/`"dark"` from `ApplicationContext.darkMode` and keep the existing resolved i18n locale; verify host-page tests cover initial light, initial dark, system preference resolution, and the current team/route/locale fields without exposing `themeMode`, DOM, storage, or auth state.
- [x] 2.2 Reuse one host context construction/post path for `fred:ready` and later value changes; track the last sent theme/locale pair and verify both theme directions and locale A-to-B send a valid context to the same ready frame while unrelated rerenders do not create an accidental duplicate or route echo.
- [x] 2.3 Test a ready/value-change race, repeated ready, team/application/target replacement, unmount, and old-frame disposal in `TeamApplicationHostPage.test.tsx`; verify latest initial values, exact source/origin admission, old listener removal, and in-flight request abort remain intact.
- [x] 2.4 Run canonical `applicationHost`, `applicationPath`, `applicationRequest`, host-page SDK integration, and existing proxy/authentication regression tests; verify route/team authorization, protected headers, refresh/retry, open-chat, and the 15-second/16-request host bounds remain unchanged.

## 3. SDK live context without new authority

- [x] 3.1 Add `onContext` to the public `FredApplicationClient` declaration and implementation in `libs/frontend/iframe-sdk/src/index.ts`; verify registration requires connection, returns idempotent unsubscribe, does not replay initial context, and preserves `connect()` resolving only once.
- [x] 3.2 Extend the admitted `fred:context` path to replace `client.context` with a frozen validated snapshot and notify every current context subscriber once for each later valid message, including identical repeats; verify light-to-dark, dark-to-light, locale A-to-B, unchanged business state, and no synthetic route callback in `iframe-sdk-client.test.mjs`.
- [x] 3.3 Apply exact origin, captured-parent source, application-ID, protocol, and parser checks to later context; verify malformed initial context fails connection, while malformed/invalid-theme/wrong-identity/unsupported later contexts leave latest state and pending requests intact with no subscriber delivery.
- [x] 3.4 Match route-subscriber exception isolation for context callbacks and clear both sets on disposal; verify one throwing listener is reported without blocking another, unsubscription stops delivery, and late context/route/reply after disposal has no effect.
- [x] 3.5 Re-run SDK route A → child B → host A, request correlation/limits, navigation, open-chat, cancellation, timeout, and disposal unit tests; verify context handling does not alter those APIs or expose parent DOM, FRED state, tokens, or translation runtime.

## 4. Prove the protocol-version decision

- [x] 4.1 Execute published SDK + pinned pre-extension host and record the existing context/route/request/lifecycle baseline; verify the exact archive and host commit identities in retained test evidence.
- [x] 4.2 Execute published SDK + extended host with optional theme and repeated context; verify the old client remains connected and its existing route/request/navigation/open-chat behavior remains correct, without claiming it exposes live context.
- [x] 4.3 Execute new packed SDK + pinned pre-extension host; verify missing theme is exposed as absent, `connect()` works with team/route/locale, and no FRED fallback theme is fabricated.
- [x] 4.4 Execute new packed SDK + extended host, including initial light/dark, both theme directions, locale A-to-B, identical repeats, malformed initial/later contexts, wrong origin/window/application ID, unsupported protocol, and team/frame replacement; verify live values and unchanged route/request/lifecycle behavior.
- [x] 4.5 Record the four-way matrix and decide protocol `"1"` only from passing evidence; if a supported old client fails, stop, revise this change for explicit protocol-`"2"` negotiation with retained version-`"1"` host support, obtain review, and do not release an unproven protocol change.

## 5. Actual archive, neutral consumer, and browser evidence

- [x] 5.1 Extend `iframe-sdk-consumer`'s neutral TypeScript fixture to import `onContext` and optional theme from the actual tarball; verify separate dependency provisioning followed by offline installation, type-check, and build outside FRED without React/UI/tokens, workspace links, or checkout fallback.
- [x] 5.2 Extend the existing distinct-origin host/child/attacker browser fixture and `browser-smoke.mjs` to exercise live context, repeats, listener removal, security rejects, route/request behavior, frame replacement, and a conflicting `?theme=dark&locale=fr` query through the installed tarball; verify host context remains authoritative, Chromium is provisioned separately, and smoke installs nothing or fetches no external resource.
- [x] 5.3 Extend SDK archive/declaration/export validation and negative tests for the new public type/method while retaining runtime-versus-declaration resolution, canonical-source evidence, complete license, dependency absence, and all existing token/UI/SDK archive guarantees; verify `pack-check` and package-specific negatives pass.
- [x] 5.4 Update `package-inputs.mjs` and CI-selection tests for the theme provider/struct, locale owner, host/protocol/SDK sources, baseline fixture, browser/consumer inputs, package metadata, and validation orchestration; verify affected changes select SDK/host gates and unrelated application changes may still skip them.

## 6. Documentation, release boundary, and review

- [x] 6.1 Update `libs/frontend/iframe-sdk/README.md`, `COMPATIBILITY.md`, applicable host/consumer docs, and `CONTROL-PLANE-PRODUCT-CONTRACT.md` after behavior passes; verify they describe live context, absent-theme consumer fallback, no SDK translation ownership, exact `hostOrigin`, and no `?theme=&locale=` synchronization or RAGS adoption claim.
- [ ] 6.2 After matrix and implementation acceptance, verify an unused SDK-only prerelease coordinate immediately before changing the SDK manifest/changelog/producer lockfile and preparing immutable candidate evidence with existing commands; verify design-token/UI versions and public exports remain unchanged and no published SDK version is overwritten. Keep fixture evidence distinct from approved release evidence.
- [ ] 6.3 After separately authorized publication through the existing independent-release process, genuinely verify the exact SDK registry archive, integrity, npm signatures, Sigstore identity, and clean consumer/browser/host gates before claiming a published context extension; verify the retained candidate and actual publishing identities match, and do not check this task from local fixtures or a workflow dispatch alone.
- [x] 6.4 Run producer quality/unit, package/archive, offline consumer/browser, host integration, and FRED application quality/build/tests under their pinned separate toolchains, with provisioning separate from offline gates; record exact commands/results and verify existing iframe/proxy/auth and token/UI regressions remain green.
- [x] 6.5 Obtain the repository-required independent implementation review, resolve in-scope findings, run `openspec validate extend-frontend-application-context --strict` and `git diff --check`, and keep this change active until its implementation and release-dependent evidence are complete.

Local evidence for completed compatibility and gate tasks is in [verification.md](verification.md).
Tasks 6.2 and 6.3 remain release-dependent and are not satisfied by the local archive or published
alpha.1 baseline. The independent review's two findings were resolved and re-reviewed.
