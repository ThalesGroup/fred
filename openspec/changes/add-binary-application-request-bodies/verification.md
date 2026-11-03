## Verification (2026-10-20)

| Check | Command | Result |
|---|---|---|
| Protocol, host page, applications | `npx vitest run src/rework/components/pages/TeamApplicationHostPage src/rework/features/applications` (apps/frontend) | 162 passed, 7 skipped (SDK integration needs a packed SDK) |
| Frontend suite | `make test` (apps/frontend) | 4419 passed, 8 skipped |
| Frontend quality | `make code-quality` (apps/frontend) | tsc, prettier, eslint clean |
| SDK client | `node --test tests/iframe-sdk-client.test.mjs` (libs/frontend) | 17 passed |
| Frontend packages suite | `make test` (libs/frontend) | 383 passed |
| Frontend packages quality | `make code-quality` (libs/frontend) | lint, prettier clean |
| Release contract | `make release-check` (libs/frontend) | passed with iframe-sdk 0.1.1-alpha.1 |
| Migration note | `make migration-check` | 1 new declaration valid |

## Compatibility matrix

| SDK | Host | Evidence |
|---|---|---|
| new (packed 0.1.1-alpha.1) | new | `node scripts/iframe-sdk-host-integration.mjs`: 8 passed, including the binary upload/download and JSON-from-Blob test |
| published 0.1.0-alpha.4 (npm) | new | same integration test with `FRED_IFRAME_SDK_ENTRY_URL` on the npm archive and `FRED_IFRAME_SDK_LEGACY=1`: 5 passed, 3 skipped (newer-SDK tests); text transport unaffected by the announcement |
| new (packed) | `origin/swift` (unchanged host) | the swift checkout's own integration test with the packed new SDK: 7 passed |
| new | host without the capability | `iframe-sdk-client.test.mjs` "keeps text and refuses binary bodies on a host without the capability": `unsupported-by-host`, nothing posted |

## Real browser

`runBrowserSmoke({ checks: ["iframeSdk"] })` (Playwright Chromium 1243, host and frame on
different origins): the production host page announced `binary-bodies`; the service mock
received exactly `[0, 255, 195, 40, 128, 127]` as `application/octet-stream` (not valid UTF-8,
so a text transport would have altered it); the frame downloaded `echo.bin` holding the
reversed bytes. The existing local Markdown download and the staged SDK consumer checks passed
in the same run.

## Not proven

- Behavior behind the real nginx gateway (`/app-services/`) and a real application service: the
  gateway rules are unchanged, and the upload ceiling (`FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE`)
  was not exercised.
- Large transfers (tens of MB): only small payloads were tested.
