## Context

The bridge has three text-only points:

- `applicationProtocol.ts`, the single protocol source that the SDK build copies, admits a `fred:request` body only as a string or null, and a `fred:response` body only as a string.
- `TeamApplicationHostPage.tsx` reads every upstream response with `response.text()` before posting it to the frame.
- The SDK rejects a non-string body and rebuilds the response from `TextEncoder().encode(body)`.

`postMessage` already clones `Blob` (and `File`) between windows, cross-origin included. `FormData` is not cloneable. The gateway's `/app-services/` location neither buffers nor times out before 3600 s; its upload ceiling is the operator's `FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE`. The SDK's 30 s request deadline is already configurable per request (`timeoutMs`).

## Goals / Non-Goals

**Goals:**

- Exact bytes both ways for any application, through the existing bridge and the host's existing authentication.
- Every published/new SDK × current/extended host combination keeps working (the four-way matrix the SDK release already runs).

**Non-Goals:**

- Streaming, upload or download progress, remote cancellation: transfers stay buffered, as text transfers are.
- Any gateway, chart or backend change; raising the default upload ceiling.
- A protocol version `"2"`.

## Decisions

**Bodies travel as `Blob`, not base64 or `ArrayBuffer`.** A `Blob` is cloned natively, carries its `type`, and `fetch` sends it as is; base64 costs a third more and an encode/decode on both sides. `ArrayBuffer` would need either a copy or a transfer list and loses the content type. Applications holding an `ArrayBuffer` wrap it in a `Blob`.

**`FormData` is serialized in the SDK.** The SDK turns a `FormData` into a `Blob` by reading it through a local `Request`, and takes that request's `content-type` (with its boundary) as the header. The host stays ignorant of forms: it only ever relays a string, a `Blob` or nothing. A caller-set `content-type` on a `FormData` request is rejected, since the boundary must match the body.

**The frame asks for a binary response; the host does not decide alone.** `fred:request` gains an optional `responseType: "blob"`, absent meaning text (no `"text"` value: nothing would send it). With `"blob"` the host reads `response.blob()` and posts it as the `fred:response` body. An older SDK never sends the field, so it never receives a `Blob` its parser would reject. The new SDK always asks for `"blob"` when the host announces the capability: `Response` decodes text and JSON from bytes exactly as `fetch` does, so applications need no new option.

**The host announces the capability in `fred:context`.** It adds an optional top-level `capabilities: ["binary-bodies"]` to the context message. A list rather than a boolean leaves room for later optional transport features without another field each time, so parsers keep its string entries and ignore anything else instead of rejecting the context. Older SDK parsers rebuild the message from known fields and drop it. The new SDK records it on connect; without it, a `Blob` or `FormData` body is refused locally with a new `unsupported-by-host` error and requests stay on text.

**Parsers stay closed.** Each parser admits a `Blob` only as a body and keeps rejecting any other body or response type (arrays, plain objects, `ArrayBuffer`). The host does not inspect or size-check the `Blob`: the gateway enforces the upload limit and the upstream status reaches the application unchanged.

## Risks / Trade-offs

- [Large transfers are held in memory twice, once in each window] → acceptable for documents in the tens of megabytes, which is the need; streaming stays a non-goal and would be a separate change.
- [An upload above the gateway ceiling fails with 413] → the application receives that status as for any HTTP error; the SDK README states the ceiling and that the operator sets it.
- [A long transfer exceeds the SDK's 30 s default] → applications pass `timeoutMs` on such requests; the README says so.
- [A newer SDK on an older host silently degrading downloads to text] → binary responses are only requested when the host announces the capability; without it the application gets today's text behavior, documented in `COMPATIBILITY.md`.

## Migration Plan

Ship the host in a Fred release and the SDK as a new `@fred-oss/iframe-sdk` version through the existing release workflow. Applications adopt it by upgrading the SDK; nothing changes for those that do not. Rollback is a host rollback: applications then fall back to the text transport, and only their binary bodies are refused.
