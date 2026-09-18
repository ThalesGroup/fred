# Proposal

## Why

Local workers serve stale editable library code and configuration. Extract the approved reload tooling fix tracked by [#2736](https://github.com/ThalesGroup/fred/issues/2736).

## What Changes

- Derive package watch directories from local uv sources for both reload targets.
- Align VS Code tasks, remove debugger reload flags while preserving ports, and document restart behavior.
- Require Uvicorn 0.35 for bounded watches on control-plane and knowledge-flow.
- Install watchfiles for fred-agents development so YAML changes trigger reload.

## Capabilities

No product capability changes; this development-tooling change uses `skip_specs: true`.

## Impact

Shared Python Make rules, VS Code configuration, fred-agents development dependencies and developer documentation. Deployment entry points stay unchanged.
