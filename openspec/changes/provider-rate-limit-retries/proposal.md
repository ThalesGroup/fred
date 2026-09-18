## Why

A transient provider rate limit aborts an otherwise useful agent turn. Extract the reviewed POC policy for ReAct and Deep parent model calls under [issue #2535](https://github.com/ThalesGroup/fred/issues/2535).

## What Changes

- Share provider throttle detection with document extraction.
- Retry only model calls, with bounded attempts and retry scheduling time, provider hints, jitter, cancellation and observable attempts.
- Wire the same policy into Deep parents; native child graph coverage belongs to the later integration layer.

## Capabilities

### New Capabilities

- `provider-rate-limit-retries`: bounded model-call retry and shared detection.

### Modified Capabilities

None.

## Impact

fred-core detector, Knowledge Flow extractor, fred-runtime middleware and Deep parent wiring. No API, profiles, filesystem backend, custom delegation, or UI changes. Issue remains open for native children.
