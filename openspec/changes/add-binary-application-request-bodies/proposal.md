## Why

A hosted application reaches its own service only through the host's request bridge, and that bridge carries text only: request bodies must be strings, and the host reads every response with `response.text()`, which corrupts binary content. An application can therefore neither upload a file nor download a generated binary (xlsx, pptx, archive) from its service. ThaNOS, the next application moving to a hosted UI, needs nine binary downloads and one upload (GitHub issue #3195).

## What Changes

- A request body may also be a `Blob` (a `File` included), cloned as is through `postMessage`. The SDK also accepts a `FormData` and sends it as a multipart `Blob` with its own `content-type`.
- A request may ask for a binary response; the host then answers with a `Blob` instead of text. The SDK asks for it whenever the host supports it, so `response.blob()`, `.arrayBuffer()`, `.json()` and `.text()` all return the service's exact bytes.
- The host announces the capability in `fred:context`. An SDK that does not know it keeps the text transport; an SDK facing a host that does not announce it refuses a binary body with an explicit error instead of letting the request time out.
- Protocol `"1"` is kept: every addition is optional, and existing hosts and applications behave as before.
- `@fred-oss/iframe-sdk` gets a new version carrying the extended `body` type.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-application-hosting`: adds a requirement for binary request and response bodies through the request bridge, next to the existing local-download requirement.
- `frontend-package-archives`: the SDK request API requirement, which today allows only string-or-null bodies and forbids promising binary or multipart bodies, now admits them behind the host's announcement.

## Impact

- Protocol source: `apps/frontend/src/rework/features/applications/applicationProtocol.ts` (copied into the SDK at build).
- Host: `TeamApplicationHostPage.tsx` (response body read as a `Blob` when asked, capability in the context message).
- SDK: `libs/frontend/iframe-sdk/src/index.ts`, its README, `COMPATIBILITY.md`, `CHANGELOG.md`, version.
- Tests: protocol, host page, host/SDK integration, SDK client, and the browser smoke.
- No backend, chart or gateway change. Upload size stays bounded by the gateway's `FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE` (10m by default, operator-set); transfers stay buffered in browser memory.
- Migration note: impact none (no operator action).
