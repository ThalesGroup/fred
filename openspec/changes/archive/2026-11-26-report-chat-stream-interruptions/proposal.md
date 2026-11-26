## Why

A managed chat stream can end while Fred is still consuming the provider response. Operators currently have to correlate proxy access logs with a generic cancelled turn, and the browser can settle silently or show raw transport error text.

Tracking issue [#3692](https://github.com/ThalesGroup/fred/issues/3692), under [#2227](https://github.com/ThalesGroup/fred/issues/2227).

## What Changes

- Emit one structured event when the managed chat response is cancelled or disconnected before its terminal event. Report an observed downstream disconnect when the transport provides evidence.
- Cancel the affected turn's active model streaming request from `fred-agents` and complete its HTTP cleanup when the chat connection closes early.
- Show one localized connection-interruption message when the browser detects an unexpected failure opening or reading the chat stream, including an early close without a terminal event.
- Preserve the existing user feedback for deliberate Stop, valid terminal events, HTTP rejections and human-input resume.
- Record deliberate Stop and unexpected disconnection separately in the Conversation Traces result column, using the exact captured stream segment.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `structured-logging` records early downstream chat-stream termination separately from the model invocation outcome.
- `managed-conversations` releases the interrupted turn's active provider stream and reports unexpected chat transport failure in the user's language.

## Impact

The runtime SSE lifecycle and scoped logging, the managed chat stream reader, the shared Conversation Traces store and catalog, English and French translations, and focused regression tests.
