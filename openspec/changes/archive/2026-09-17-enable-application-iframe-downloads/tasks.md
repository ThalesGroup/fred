## 1. Host permission and focused regression

- [x] 1.1 Add `allow-downloads` to the admitted iframe in `TeamApplicationHostPage.tsx`; verify the rendered host frame has the five reviewed sandbox tokens and no top-navigation or popup-escape token.
- [x] 1.2 Extend `TeamApplicationHostPage.test.tsx` with exact allowed/forbidden sandbox assertions, retaining personal-space/unauthorized frame denial and same-origin/separate-origin admission cases; run the focused Vitest host suite without weakening existing handshake, origin/source, route, request-broker, or lifecycle assertions.

## 2. Real-browser production-host evidence

- [x] 2.1 Extend the existing `libs/frontend` local Chromium/Playwright browser infrastructure with a fixture that mounts the real `TeamApplicationHostPage` for an authorized team/application and serves a child with a visible Blob download action; verify the fixture uses the production component and local-only resources, preferably with a distinct loopback child origin.
- [x] 2.2 Wire that fixture into the selected browser compatibility gate; verify Playwright receives a download from the hosted child and matches its filename and saved Markdown bytes, while the current cross-origin SDK browser regressions still pass. If direct production-host coverage can only use same-origin, record that limit and pair it with the existing cross-origin checks.

## 3. Compatibility and acceptance

- [x] 3.1 Run the focused production-host and packed-SDK integration suites (`apps/frontend` host Vitest files and `cd libs/frontend && make host-integration`); verify protocol `"1"`, source/origin rejection, protected headers, host bearer handling, and request routing remain green.
- [x] 3.2 Run `make code-quality` from the repository root, `cd apps/frontend && make test build`, and the relevant `libs/frontend` browser gate with its separately provisioned Chromium/consumer prerequisites; record exact results, independent review findings, and confirm no SDK/UI/token package source, version, release, CI workflow, backend, or RAGS code changed.
