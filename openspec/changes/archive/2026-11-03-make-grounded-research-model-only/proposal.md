## Why

The developer wants the packaged `grounded-research` procedure to be invoked
only by the model. It currently defaults to both user and model invocation,
so it appears in user commands and accepts explicit selections.

Tracking: [#3402](https://github.com/ThalesGroup/fred/issues/3402).
The previous catalog consolidation is archived; this is a focused follow-up.

## What Changes

- **BREAKING**: Make packaged `grounded-research` model-only. Remove it from
  user commands and reject direct selections through the existing eligibility
  checks, while retaining autonomous ReAct and native Deep loading.
- Extend the existing packaged eligibility and instruction-delivery tests.
- Reconcile the packaged invocation matrix and existing migration guidance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: Change `grounded-research` from user/model invocation
  to model-only invocation in the packaged catalog.

## Impact

Packaged skill frontmatter, runtime skill tests, the existing capability spec
and `docs/swift/ops/migrations/platform-skills-evolution.md`. The existing
eligibility contract supplies enforcement; no new API, loader, storage or
frontend implementation is required.
