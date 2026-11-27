## Context

The C2 incident produced a frontend proxy `499`, a cancelled runtime turn and a later successful model call. These events describe separate lifetimes. The runtime route owns the outgoing SSE response, and the browser's shared stream reader already tracks terminal events and deliberate aborts.

## Goals / Non-Goals

**Goals**

- Give operators a bounded event that can be joined to existing runtime and proxy diagnostics.
- Give a person still in the chat a useful message even when the response closed before any SSE event could reach the browser.
- Release the cancelled turn's provider HTTP request from the runtime that owns it, including while it waits for response headers.

**Non-Goals**

- Provider-side generation or billing guarantees, execution retries and recovery beyond the existing chat lifecycle.

## Decisions

1. **Report the response outcome at the SSE boundary.** Use request-local state in the managed streaming response and the existing scoped logging context. Observe downstream termination and whether a terminal event was sent. Emit `event=chat_stream_interrupted` once at INFO, with a bounded `reason` (`downstream_disconnect` for observed transport evidence, `cancelled` for cancellation of uncertain origin). Reuse owned request and correlation references and admitted conversation references when available. The generic execution completion event and provider telemetry remain independent. Emitting this from the provider wrapper would correlate the wrong lifetime.
2. **Use a browser-owned translated error for transport failures.** Reuse the shared stream reader's terminal checks and existing error notification path. Translate browser transport failures when opening or reading the stream and an EOF without a terminal event. Use the same key for normal sends and human-input resumes. Keep HTTP rejections and received runtime errors on their established paths. The frontend retains its own knowledge of deliberate aborts, which the server generally observes as an ordinary disconnect.
3. **Propagate cancellation through the existing SSE response lifecycle.** Race one SSE producer task against one ASGI disconnect listener so a disconnect can be observed even while the producer is waiting for the provider. Count receive-side disconnects before response EOF and send-side disconnect errors as transport evidence. Deliver a single cancellation to the unfinished producer and wait for it to unwind through the existing shielded cleanup. This lets LangGraph cancel its node and lets the provider SDK close the HTTP response, including before the first provider fragment. This boundary serves all managed execution engines and avoids provider-specific cancellation code. Loopback tests cover ASGI 2.3 and 2.4, provider closure before headers and between fragments, and an unrelated request that keeps running on the same client.

## Risks / Trade-offs

- A terminal event can race with a transport close. Record the backend terminal event only after a successful ASGI send and avoid replacing a terminal outcome already handled by the browser.
- Cancellation during cleanup can hide context. Use the current request's owned references and keep emission synchronous and bounded. The producer and listener stay on the serving replica, with no queue, extra network request, shared cancellation state or per-fragment task.
- The producer can be blocked reading the provider or writing an SSE frame. Verify both paths release the response and complete existing run, checkpoint and child cleanup. Reuse the configured HTTP pool for subsequent and concurrent requests.
- A browser or tab that has already closed cannot display feedback. The notification applies to a live chat observing the failure, and uses its existing stale-turn and intentional-abort guards.

## Migration Plan

Deploy via the normal runtime and frontend release. The runtime cancellation and logging are local to each response, and the frontend detects interruption from its existing stream, so either component can roll out first.

## Conversation Traces results

- The browser generates an opaque segment reference before opening the request and sends it to the runtime in the managed SSE request headers. The explicit Stop action sends an authenticated, idempotent stop request for that exact segment. It aborts the chat request immediately, independently of delivery of the stop signal. An admission race or transient database contention may retry the stop request once.
- The Control Plane validates the session owner and uses its existing row locks and per-segment receipts to attach the signal. It can arrive before or after the runtime's disconnect facts. The marker belongs to that segment and cannot change a completed result, a runtime failure or the result of another segment.
- A confirmed downstream disconnect on an unfinished recorded capture reports the existing stream-interruption category with an unknown turn outcome through trace finalization. The Control Plane stores its presentation result on the existing turn row. The turn remains eligible for resume, and later accepted facts supersede an earlier cutoff. Catalog and detail distinguish a verified stop request from a disconnect with no matching request.
- Add a nullable result and partially indexed segment references to the existing trace table. Track the result segment independently of the newly admitted segment so a late signal can still explain an interruption while a resume starts. Old clients can ignore the response field, old Control Plane ignores the interruption category on a non-terminal fact, and clients with no stop reference keep normal transport cancellation. Rollout does not require changing retained traces or provider infrastructure.
