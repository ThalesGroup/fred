# Design

## Context

Fred injects the same sync and async HTTPX clients into model SDKs. The captured Mistral Medium streams establish a real ID before sending the string `"null"` on subsequent argument fragments. The gateway address is deployment-specific.

## Decisions

- Treat the resolved POST Chat Completions route and a successful SSE response as the protocol boundary. Require a real ID already observed for the same choice and tool index before correcting an arguments-only fragment. A model-family or host allowlist would miss aliases and require deployment-specific addresses. The wire-level guard protects legitimate initial IDs and allows the same handling on any Chat Completions route.
- Add the default-on `normalize_streamed_tool_call_ids` model setting with an explicit false opt-out. The factory consumes the setting before SDK construction and carries the opt-out to the shared transport as local request metadata. Any internal header used to convey it through the SDK is removed before network I/O.
- Wrap the public sync and async HTTPX transports used by the shared clients, including proxy mounts. Keep HTTPX responsible for TLS, timeouts, pooling, and content decoding. Transform decoded bytes incrementally, dropping stale encoding and length headers on the replacement stream and retaining other response metadata.
- Bound framing and remembered tool indexes per response. Forward oversized events unchanged and resume framing at the next event boundary. Close the upstream stream on completion, consumer close, and cancellation. Avoid provider-specific overrides of LangChain's private chunk converter.

## Risks / Trade-offs

A malformed or oversized event can hide a tool-call start. Forget earlier IDs across such an event so later fragments cannot attach to an uncertain call. Test network chunk boundaries, proxy selection, concurrency, and response cancellation at the public seams.

## Migration Plan

Normal deployment enables the correction. To disable it for one model, set `normalize_streamed_tool_call_ids: false` under that model's `settings`. Existing checkpoints are outside the fix. Normal rollback restores the prior stream handling.
