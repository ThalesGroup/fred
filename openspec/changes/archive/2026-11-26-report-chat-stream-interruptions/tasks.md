## 1. Runtime diagnostic

- [x] 1.1 Emit one structured interruption event at the managed SSE response boundary. Cover an ASGI disconnect while waiting for the first event, cancellation without transport evidence, and a close after a terminal event in focused backend tests.
- [x] 1.2 Verify that interleaved managed streams retain distinct request and conversation references and that the serialized diagnostic excludes prompt, response and exception text.

## 2. Provider stream cancellation

- [x] 2.1 Propagate one cancellation to the SSE producer and await its teardown. Drive the managed ASGI response with a local provider and verify cancellation both before provider headers and during its response body.
- [x] 2.2 Test a downstream disconnect while writing a frame and concurrent turns sharing the client. Verify the interrupted model call ends, existing cleanup runs, and the other turn completes normally.

## 3. Managed chat feedback

- [x] 3.1 Localize transport failures and premature EOF through the existing chat notification path. Cover an opening failure, a read failure and a clean EOF without a terminal event, including an accepted human-input resume.
- [x] 3.2 Verify intentional Stop and a superseded view stay silent, and valid terminal events and HTTP rejections retain their existing presentation. Check the English and French message keys.

## 4. Verification and close-out

- [x] 4.1 Run focused runtime and frontend suites, root code quality and the applicable author, independent and performance reviews. Record test and review results in the PR or this checklist.
- [x] 4.2 Document the event, cancellation and chat behavior in the existing runtime, observability and UX guidance and include the operator migration note. Validate, sync and archive the reconciled OpenSpec change.

The runtime suite passed 2,733 tests and the frontend suite passed 5,513. Root code quality covered all modules in two passes after the first process stopped. Independent and performance review verified the ASGI 2.4 path and shared client isolation after the review findings were addressed.

In the local application, an injected disconnect displayed the French notification. Fred logged the interruption and closed the simulated provider connection 22 ms after the cut, before receiving a model fragment. The Conversation Traces timeline showed both streams closing without a terminal frame, with a persisted checkpoint.

## 5. Distinguish the two results in Conversation Traces

- [x] 5.1 Bind the browser's explicit Stop signal to the exact runtime trace segment. Persist confirmed early downstream disconnection in existing trace finalization.
- [x] 5.2 Store and display the resolved result for captured turns. Verify both arrival orders, session ownership, duplicate and stale signals, completed turns, and continuation after a stopped or interrupted segment.
- [x] 5.3 Exercise deliberate Stop and injected connection loss in the local application and verify both French results in the catalog. Regenerate API bindings, review and verify the branch, and sync and archive the final change.

The final local application run showed Arrêt demandé for a click while the proxy held response headers, and Flux interrompu for an injected cut. Each catalog filter returned its matching trace. Both simulated provider connections closed before their first fragment. A second Control Plane instance accepted the Stop signal while the first handled trace admission and finalization. Both checkpoints persisted.

The final focused verification covered 25 runtime cases, the delegated response CORS check, 34 Control Plane trace cases, and 244 frontend cases. Root code quality, generated API bindings, and independent review passed. Review findings about early Stop, resumed segments, catalog selection, and bounded writes were covered by the final checks.
