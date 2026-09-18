## Why

Capability tools supplied through middleware bypass the binder's trace span and disappear between model calls. This extracts the reviewed POC correction for [#2742](https://github.com/ThalesGroup/fred/issues/2742), preserving current upstream error handling.

## What Changes

- Trace middleware-contributed tools on ReAct and Deep, with one span per invocation.
- Share span parenting, cancellation/error termination, and opt-in content capture with binder tools.
- Classify runtime-tool spans as Langfuse tool observations.

## Capabilities

### New Capabilities

- `capability-tool-tracing`: shared tool span coverage and lifecycle on ReAct and Deep.

### Modified Capabilities

None. Existing completed `reliable-agent-work-completion` error classification is preserved.

## Impact

Runtime tracing, binder metadata, ReAct/Deep middleware frames and Langfuse adapter; focused offline regressions and runtime contract documentation. No API, dependencies, filesystem backend or custom delegation package changes. Native-child middleware composition remains a later extraction layer.
