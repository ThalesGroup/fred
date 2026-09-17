## Context

See [proposal.md](proposal.md) and the [hosting delta](specs/frontend-application-hosting/spec.md). `TeamApplicationHostPage.tsx` currently renders admitted applications with `sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`. Because `allow-downloads` is absent, an application can correctly create a Markdown Blob, object URL, and `<a download>` yet have the browser block the download. RAGS has that child-side flow and needs no upstream file URL or token for the generated content. FRED's host owns the sandbox; the npm iframe SDK does not.

The host admits only a catalog-authorized collaborative-team application, accepts protocol-`"1"` frame messages after exact source-window and configured-origin checks, and brokers relative application-service requests with host-owned bearer handling. Its same-origin mode is already a rendering/lifecycle boundary, not isolation from malicious same-origin code; separate-origin mode retains exact-origin messaging. The hosting RFC is historical design context, while the current host and control-plane contract establish shipped behavior. `frontend-package-archives` owns package and compatibility gates, not this browser permission.

The existing host unit and packed-SDK integration tests use happy-dom. `libs/frontend/scripts/browser-smoke.mjs` uses real Chromium and distinct loopback origins, but its iframe SDK host is a fixture implementation, not `TeamApplicationHostPage`. Browser evidence must exercise the production host component.

## Goals / Non-Goals

**Goals:** Enable ordinary local Blob downloads for every admitted hosted application; retain existing host authority and browser sandbox restrictions; prove the actual host behavior in Chromium with known filename and bytes.

**Non-Goals:** Introduce a file-transfer message, download service, SDK API, RAGS-specific behavior, package release, backend route, storage URL, deployment setting, or a stronger claim that a same-origin frame is a security boundary.

## Decisions

### Use the browser sandbox permission

Add only `allow-downloads` to the production iframe's existing sandbox tokens. This permits a child-owned Blob/object-URL plus anchor download without transferring bytes through the host. No protocol, request, authentication, or package change is needed. The permission applies to all trusted team-owned applications admitted by this host. It broadens their browser capability to create downloads, including potentially programmatic downloads; FRED does not claim to enforce a human gesture for every download. The RAGS flow itself is user-triggered.

**Alternative — host-mediated download message:** A child-to-host API would add parser, type, SDK, and host behavior, likely require an iframe-SDK release, and create compatibility and payload-size/content-transfer questions. A host message alone would not prove transient browser user activation. The existing contract reserves messages for FRED authority such as authenticated requests and routing; local child-owned bytes do not need that authority. Reject this expansion for the stated use case.

**Other mechanisms:** Existing `fred:request` carries buffered application-service text through the host, but does not grant a browser download. A direct upstream download URL would introduce authentication and origin behavior that the local Blob does not require. No smaller established FRED mechanism was found. Do not add a parallel download service.

### Keep authority and containment checks intact

The application gains browser file creation/download capability. The host still does not send its bearer, Keycloak object, store, or upstream service address to the frame; relative paths continue through the existing broker with its protected-header rules, refresh handling, and team scope. The new token does not authorize parent route changes, top navigation, or popup sandbox escape. Keep `allow-scripts`, `allow-same-origin`, `allow-forms`, and `allow-popups`; do not add `allow-top-navigation`, `allow-top-navigation-by-user-activation`, or `allow-popups-to-escape-sandbox`. Preserve frame admission, source/window and origin checks, protocol `"1"`, the handshake, lifecycle, and the same host contract for same-origin and separate-origin configured URLs. No FRED DOM/API dependency is added for child code.

This is a narrow browser-permission increase within the established first-party/team-owned application trust model. Because scripts plus same-origin are already allowed, the same-origin deployment must not be described as a hardened sandbox against malicious child code. The reviewable guarantee is that this change adds no further FRED authority or unrelated sandbox tokens; stronger isolation would require a separate-origin deployment and separate design.

### Prove the browser result through the production host

Extend the existing local Chromium/Playwright and loopback-server infrastructure with a lean browser fixture that mounts the real `TeamApplicationHostPage` under controlled authorized team/catalog inputs. Serve a child page from a distinct loopback origin where feasible, using the configured absolute `ui_prefix`, and provide a visible download action that creates known `text/markdown` Blob bytes, sets a known filename on `<a download>`, clicks it, and revokes the object URL. Use Playwright's download event, suggested filename, and saved file bytes to assert completion. The fixture needs no network source for the file data. The test must fail if it renders a copied iframe markup or simulated host instead of the production component. If mounting the separate-origin variant in this harness proves impractical, directly test same-origin production hosting and retain the existing cross-origin SDK/host regressions; document that coverage limitation in verification evidence.

In `TeamApplicationHostPage.test.tsx`, assert the exact allowed token set and absence of the high-risk tokens. Keep authorization/personal-space frame denial and same-origin/separate-origin admission tests; run existing handshake, wrong-origin/source, route, request-broker, bearer/protected-header, lifecycle, and packed-SDK host integration regressions. A sandbox DOM assertion alone cannot prove a browser download.

### CI and package scope

`.github/workflows/Check-pending-requests.yml` already selects frontend checks for `apps/frontend/**`, and its `frontend-packages` filter explicitly includes the production host page and both host test files. `libs/frontend/scripts/package-inputs.mjs` likewise lists them as host compatibility inputs. A browser regression placed under `libs/frontend/**` selects the package compatibility job, whose fixture validation invokes Chromium browser smoke and host integration through existing gates. No CI workflow edit or `frontend-package-archives` delta is required for these planned paths. Keep the new production-host browser check in a selected gate rather than a manual-only script.

Protocol `"1"`, `@fred-oss/iframe-sdk`, `@fred-oss/ui`, and `@fred-oss/design-tokens` remain byte-for-byte unchanged; no version bump, manifest change, release candidate, npm workflow, or publication is needed. No backend API or deployment schema changes are needed for a local Blob.

## Risks / Trade-offs

- **All admitted applications can initiate downloads, not only a user-click flow** → Limit admission to the existing trusted team-application catalog and retain all other sandbox and host authority checks; review the broader browser capability explicitly.
- **A synthetic DOM test could pass while Chromium blocks downloads** → Require the real production component and Playwright download event plus filename and byte checks in CI.
- **A simulated browser host could mask the production token** → Mount/import the real host component in the new browser fixture and assert its frame sandbox before the download action.
- **The same-origin frame is not malicious-code isolation** → State this existing limitation explicitly and avoid treating the sandbox token as an authorization boundary.

## Migration Plan

Ship the host sandbox token with its focused and real-browser regressions. Existing protocol-`"1"` applications require no migration. Rollback is removal of `allow-downloads` from the host sandbox, restoring prior download blocking; there is no stored data, migration, package, or protocol rollback. This FRED change unblocks the RAGS synthesis download without adding RAGS-specific FRED API semantics.
