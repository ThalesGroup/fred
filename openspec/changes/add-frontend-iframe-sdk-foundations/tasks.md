## 1. Tracking and compatibility baseline

- [ ] 1.1 Create or confirm the dedicated GitHub tracking issue, link it from `proposal.md`, and verify neither closed package-foundation issue was repurposed.
- [ ] 1.2 Inventory every import and caller of `applicationHost.ts`, `applicationPath.ts`, and the protected-header/request helpers, including raw or dynamically constructed protocol messages; record the intended compatibility re-exports and verify the inventory with repository-wide searches.
- [ ] 1.3 Add golden protocol-`"1"` tests for all eight current serialized message shapes, optional-field normalizations, six methods, ID/header limits, and malformed inputs; verify the tests pass against the pre-extraction behavior before moving definitions.
- [ ] 1.4 Record the audited RFC discrepancies in the implementation documentation plan—illustrative API, deferred theme/live locale, buffered text transport, ordinary HTTP(S) origins, and no opaque/`null` origin—and verify no task relies on a stale RFC statement.

## 2. Canonical protocol extraction

- [ ] 2.1 Create the transport-neutral canonical `applicationProtocol.ts` with protocol constants, cloneable context/message types, request methods and limits, and pure frame/host parsers; verify it imports no React, router, authentication, backend, catalog, or host-state module.
- [ ] 2.2 Move the existing relative-path validation and protected-header identification into the canonical protocol boundary while preserving compatibility re-exports from the current modules; verify all current callers compile without application behavior loss.
- [ ] 2.3 Update `applicationHost.ts`, `applicationPath.ts`, and `applicationRequest.ts` to consume the canonical definitions, and verify golden host/path/request tests preserve exact normalization, rejection, and header behavior.
- [ ] 2.4 Extend parser and path tests for host-to-frame messages, complete context validation, unsupported versions, malformed nested values, encoded traversal, and protected-header casing; verify pure validation rejects each mutation without browser or host state.

## 3. Framework-independent child client

- [ ] 3.1 Add the `@fred/iframe-sdk` workspace member, public root/protocol source boundaries, development manifest, FRED license, and README skeleton; verify the manifest exposes only `.` and `./protocol` and declares no dependencies or peer dependencies.
- [ ] 3.2 Implement origin/application configuration and the shared `connect()` lifecycle with listener-before-ready ordering, immediate plus 500 ms ready retries, a default 10-second deadline, exact parent/source/origin admission, and stable typed failures; verify focused unit tests cover valid, raced, concurrent, malformed, mismatched, timed-out, missing-parent, and disposed connection cases.
- [ ] 3.3 Implement immutable context access and route subscriptions with idempotent unsubscribe; verify every accepted route event is delivered once to each current subscriber, identical `subPath` values are not deduplicated, and wrong-origin/window, pre-context, malformed, and post-disposal messages cannot notify consumers.
- [ ] 3.4 Implement validated `navigate()` and `openChat()` intents with normalized replace and nullable session fields; verify valid wire shapes and local rejection of every unsafe path class before any postMessage call.
- [ ] 3.5 Implement request serialization with collision-checked IDs, allowed methods, string-or-null bodies, ordinary string headers, case-insensitive protected-header rejection, and the 16-request client bound; verify invalid requests and the seventeenth pending request fail locally without posting.
- [ ] 3.6 Implement out-of-order response correlation, default/per-request 30-second deadlines, `AbortSignal`, generic transport errors, and duplicate/unknown/late-response suppression; verify cancellation releases only local state and no mutation is retried.
- [ ] 3.7 Reconstruct browser `Response` objects for success and non-OK HTTP statuses, using null bodies for HEAD and 204/205/304; verify JSON/text, 401/403/5xx, headers, transport-error, and every bodyless case.
- [ ] 3.8 Implement idempotent disposal that rejects connection and pending work and removes listeners, timers, abort hooks, and subscribers; verify subsequent calls and messages from the disposed lifecycle have no effect.

## 4. FRED host and legacy-client compatibility

- [ ] 4.1 Update canonical host-page tests to exercise legacy raw clients after extraction and the new canonical protocol surface; verify all eight existing shapes retain their serialized fields, defaults, and effects without a version change.
- [ ] 4.2 Add SDK/current-host compatibility coverage for ready/context, route, navigation, open-chat, requests, duplicate IDs, and response errors, including host route A, child navigation to B, then host route A; verify both accepted A events reach current subscribers, request responses remain deduplicated by request ID, the host needs no protocol adapter, and the SDK sends no operation before context.
- [ ] 4.3 Extend frame/team lifecycle tests for application, target, team, and unmount replacement; verify old listeners are removed, fetches are aborted, late replies are suppressed, and stale frames cannot affect the new lifecycle.
- [ ] 4.4 Run focused application host, request, path, TeamApplicationHostPage, authorization/token-refresh, and proxy suites; verify the 15-second host deadline, 16-request host bound, source/origin checks, protected-header defense, bearer/refresh policy, route ownership, and proxy behavior remain green.

## 5. SDK generation and archive validation

- [ ] 5.1 Extend the producer's exact input inventory and generator to copy the canonical protocol and allowlisted client sources into disposable generated input; verify recorded paths/hashes and the reviewed module graph fail on missing, extra, or changed inputs.
- [ ] 5.2 Build deterministic ESM JavaScript and closed declarations for both public entry points; verify positive build fixtures contain runtime imports/exports that close over executable packed modules and declaration references/`types` exports that close over packed `.d.ts` files, with no bundled Node code, framework/FRED dependency, source alias, absolute path, or undeclared module.
- [ ] 5.3 Add an SDK archive validator using the shared tar safety checks and distinct runtime and declaration resolvers: runtime imports/exports must reach executable packed modules, while declaration references and `types` exports may reach valid packed `.d.ts` files; verify positive tests for both resolution paths and the real `npm pack` archive pass.
- [ ] 5.4 Add disposable negative archive mutations for missing/extra files, unsafe paths or links, wrong exports/metadata/license/evidence, runtime imports or exports with only declaration targets, declaration references or `types` exports without valid `.d.ts` targets, checkout/workspace references, local protocols, and undeclared or framework dependencies; verify each mutation fails for its intended resolver and reason.
- [ ] 5.5 Run the combined producer generation, quality, unit, pack, and archive suites; verify all existing token/UI positive and negative assertions pass unchanged alongside the SDK.

## 6. Isolated neutral consumer

- [ ] 6.1 Add a framework-neutral TypeScript/browser fixture and lockfile that imports the client root and protocol entry point without React or another FRED package; verify its dependency graph contains only the declared pinned tooling and the staged SDK archive.
- [ ] 6.2 Extend provisioning to populate a dedicated cache from the fixture lockfile and report the pinned browser-install command separately; verify provisioning is the only consumer step permitted to access the network.
- [ ] 6.3 Install the actual SDK tarball and cached tooling into a fresh OS temporary directory outside FRED using npm offline mode, then type-check and build; verify there are no workspace/local links, FRED checkout paths, FRED `node_modules` resolution, React, or network fetches.
- [ ] 6.4 Add missing-cache and missing-browser prerequisite checks; verify offline validation and browser smoke fail actionably instead of downloading, using FRED dependencies, or bootstrapping Chromium.

## 7. Cross-origin browser validation

- [ ] 7.1 Extend the existing harness with separate loopback host and child servers, stage only the isolated build and packed protocol surface, and load the child through a real iframe; verify browser origin and `WindowProxy` identities are distinct and all resource responses are successful and local.
- [ ] 7.2 Add browser cases for ready retry, matching context, route subscription, host route A followed by child navigation to B and host route A again, navigation, open-chat, and two out-of-order requests; verify each accepted route message is delivered once without sub-path deduplication while response settlement remains deduplicated by request ID in the installed SDK.
- [ ] 7.3 Add browser cases for buffered JSON/text success, 401/403/5xx Responses, generic transport failure, and HEAD/204/205/304 bodyless Responses; verify Fetch-like observable results without streaming or binary claims.
- [ ] 7.4 Add browser cases for malformed messages, unsupported context, wrong application ID, wrong origin/window, sibling/popup/stale frame impersonation, and unsafe paths/headers; verify no unadmitted event changes client or host state.
- [ ] 7.5 Add browser cases for pending capacity, connection/request deadlines, local abort, duplicate/unknown/late replies, disposal, and frame/team replacement; verify local resources are released and old lifecycles cannot affect replacements.
- [ ] 7.6 Make browser request monitoring reject non-loopback, `file:`, external-service, checkout-path, failed, and non-successful resource requests, and verify smoke performs no installation or browser provisioning.

## 8. Commands, CI selection, and documentation

- [ ] 8.1 Add producer/root commands for SDK generation, unit tests, packing, archive checks, isolated consumption, and browser smoke while preserving existing aggregate commands; verify each focused command and the aggregate frontend-package gate execute the intended stages exactly once.
- [ ] 8.2 Extend CI input classification for every SDK source, canonical protocol/path input, producer manifest/lockfile, build/validator/shared archive script, fixture/lockfile, browser harness, license, README, Makefile, and workflow input; verify table-driven positive selection tests cover each class.
- [ ] 8.3 Preserve negative CI-selection behavior for unrelated application files and require both package and application gates for canonical protocol/path or declared host-compatibility inputs; verify selector tests distinguish these cases exactly.
- [ ] 8.4 Complete the SDK consumer README and producer README with public API, explicit origin/application configuration, buffered text/JSON semantics, limits, local-only timeout/cancel behavior, host authority, offline/provision commands, and unsupported features; verify every documented import resolves from the packed archive.
- [ ] 8.5 Update the durable control-plane application-hosting contract and affected frontend guidance to identify the canonical protocol source and SDK boundary; verify authentication, authorization, routing, refresh, and proxy ownership remain assigned to FRED.
- [ ] 8.6 Correct only the existing frontend-packaging RFC's newly stale implementation-status and suggested-location statements while leaving theme/live locale, publication, registry adoption, and external adopter work open; verify links still target the single existing RFC.

## 9. Completion evidence

- [ ] 9.1 Run the repository-pinned producer install/provisioning, quality, unit, deterministic generation, pack, token/UI/SDK archive mutation, isolated offline-consumer, and cross-origin browser commands; record exact commands and successful results in this checklist without conflating provisioning with offline execution.
- [ ] 9.2 Run the repository-pinned frontend quality, production build, complete tests, and focused host/request/path/page/proxy/authentication regressions; record exact commands and results, or an actionable environmental blocker without weakening acceptance.
- [ ] 9.3 Run strict OpenSpec validation for `add-frontend-iframe-sdk-foundations` and `git diff --check`; verify both pass and all implementation evidence is linked before checking the final task.
- [ ] 9.4 Obtain the repository-required independent implementation review, resolve every in-scope finding, and record findings/resolutions; verify no package was published, no registry/RAGS/SDK adoption occurred, and the change and tracking issue remain open for review.
