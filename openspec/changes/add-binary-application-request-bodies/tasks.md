## 1. Protocol

- [x] 1.1 In `applicationProtocol.ts`, admit a `Blob` or null or string as `fred:request` body, an optional `responseType: "blob"`, a `Blob` or string as `fred:response` body, and an optional `capabilities` list on `fred:context` whose unreadable entries are ignored; verify `applicationProtocol.test.ts` covers each accepted shape and rejects `ArrayBuffer`, plain objects, arrays and other response types.

## 2. Host

- [x] 2.1 In `TeamApplicationHostPage.tsx`, announce `capabilities: ["binary-bodies"]` in the context message, forward a `Blob` request body upstream as is, and read the response with `blob()` when the frame asked for `"blob"`; verify `TeamApplicationHostPage.test.tsx` shows the exact upstream body and content type for a `Blob`, a `Blob` response posted to the frame, and a text response when `responseType` is absent.

## 3. SDK

- [x] 3.1 In `iframe-sdk/src/index.ts`, accept `Blob` and `FormData` bodies (a `FormData` serialized to a multipart `Blob` with its own `content-type`, a caller `content-type` refused), record the announced capabilities on connect, ask for `"blob"` responses when announced, and refuse binary bodies with `unsupported-by-host` otherwise; verify `tests/iframe-sdk-client.test.mjs` covers each case including a text request on a host without the capability.
- [x] 3.2 Rebuild the response from a `Blob` body and keep the text path for string bodies; verify an upload and a download round-trip with exact bytes, and JSON/text reads of a `Blob` response, in `TeamApplicationHostPage.sdk-integration.test.tsx`.

## 4. Compatibility and browser evidence

- [x] 4.1 Run the four-way matrix (`npm run test:host-integration`) with the published `0.1.0-alpha.4` SDK and the new SDK against the current and extended host; verify the older SDK stays on text with the new host and the new SDK refuses binary bodies on the old host.
- [x] 4.2 Extend the production-host browser fixture (`libs/frontend/fixtures/production-host/`) with a binary upload and download and verify `npm run test:browser` checks the bytes on both sides.

## 5. Documentation and release

- [x] 5.1 Update the SDK `README.md` (body types, the upload ceiling set by the operator, `timeoutMs` for long transfers) and `COMPATIBILITY.md` (binary bodies and the four combinations); verify no remaining text says the transport is text-only.
- [x] 5.2 Bump `@fred-oss/iframe-sdk` to `0.1.1-alpha.1` with a `Review: approved` `CHANGELOG.md` entry; verify `make -C libs/frontend release-check` passes.
- [x] 5.3 Add the migration note (impact none) under `docs/swift/ops/migrations/`; verify it follows `MIGRATION-NOTE-TEMPLATE.md`.

## 6. Verification and close-out

- [x] 6.1 Run `make code-quality` and `make test` in `apps/frontend` and `libs/frontend` and record the results in this change.
- [ ] 6.2 Reconcile the change with the implementation, archive it into `frontend-application-hosting`, and update issue #3195.
