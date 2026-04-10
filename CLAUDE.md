# CLAUDE.md

Repository-wide instructions for Claude Code.

## Mandatory Read Order

1. [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md)
2. [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)
3. [`docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
4. [`docs/platform/REBAC.md`](./docs/platform/REBAC.md) when access/team behavior is touched

## Non-Negotiable Defaults

- Keep scope minimal. No over-engineering.
- Use existing conventions and existing Make targets.
- Run `make code-quality` and `make test` in each touched project.
- Keep default tests offline. Any external dependency test must be marked `integration`.

## Fred Runtime Topology

Canonical source:

- [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)

This defines:

- Agentic API vs Knowledge Flow API vs Control Plane API responsibilities.
- Knowledge Flow / Agentic / Control Plane Temporal worker responsibilities.
