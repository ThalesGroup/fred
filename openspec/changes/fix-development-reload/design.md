# Design

## Context

See proposal.md. All current backend local sources use inline TOML tables and top-level Python packages.

## Goals / Non-Goals

**Goals:** Reload local app, declared dependency packages and YAML configuration without watching whole repositories.

**Non-Goals:** Production reload, personal debugger port changes, new dependency resolution architecture.

## Decisions

Reuse the POC Make discovery from `[tool.uv.sources]`; select directories containing `__init__.py` and exclude sibling tests. Add app config and YAML filtering. Keep debugger sessions single-worker and route reload through maintained Make targets. Add watchfiles to fred-agents development dependencies, since plain uvicorn otherwise falls back to Python-only polling.

Uvicorn 0.34 forcibly adds the working directory and violates the bounded-watch
requirement. Upgrade control-plane and knowledge-flow to `>=0.35,<0.36`;
regenerate their locks without unrelated package upgrades.

## Risks / Trade-offs

- Inline TOML parsing and top-level package discovery match this repository, not arbitrary Python layouts. Document this constraint; a layout change requires updating the tooling.
- Watcher support must be present: verify real file notifications using Uvicorn's watchfiles supervisor without booting dependent services.

## Lifecycle note

The approved POC patch was applied before these extraction artifacts were created. This ordering deviation is recorded rather than presented as advance planning. The extraction scope was already approved in the handoff.
