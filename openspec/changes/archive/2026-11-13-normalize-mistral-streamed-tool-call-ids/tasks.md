# Tasks

## 1. Reproduce and fix the stream

- [x] 1.1 Reproduce the split call through Fred's model factory and public sync streaming with a synthetic round 56 fixture.
- [x] 1.2 Add bounded response framing, call-index normalization, sync and async transport wrappers, and factory opt-out wiring. Verify original IDs and tool-result pairing through both public model streaming APIs.

## 2. Verify and document

- [x] 2.1 Verify fragmented and interleaved events, legitimate IDs, concurrent streams, early closure, cancellation, proxy routing, compressed bodies, and out-of-scope responses using offline tests.
- [x] 2.2 Replay the 18 archived streams offline and run the Fred core tests and root quality checks. Obtain independent branch and performance review.
- [x] 2.3 Document the opt-out and ordinary upgrade in the migration note and archive the completed change.

## Verification

- The synthetic round 56 test reproduced a nameless call before the fix. Offline replay through the model factory recovered all 18 archived streams.
- Fred core passed 1,322 offline tests before the review fixes. All 60 model tests passed after adding the mixed-line-ending and HTTP/1.1 drain regressions.
- Targeted Ruff and Basedpyright checks and the migration note check passed. Root code quality ran 28 migration tests, then stopped during the Fred pod environment bootstrap at `ensurepip`.
- Independent review against `swift` at `b58e995f8` checked transport and SDK behavior, proxy and timeout handling, config propagation, and connection lifecycle. The mixed SSE delimiter and async drain findings have regression tests. Verification used mock and archived streams.
