# Fred Copilot Instructions

## Mandatory Read Order

1. [`docs/DEVELOPER_CONTRACT.md`](../docs/DEVELOPER_CONTRACT.md)
2. [`docs/PLATFORM_RUNTIME_MAP.md`](../docs/PLATFORM_RUNTIME_MAP.md)
3. [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](../docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
4. [`docs/REBAC.md`](../docs/REBAC.md) for team/access work

## Non-Negotiable Defaults

- Keep implementation minimal and direct.
- Do not over-engineer.
- Run `make code-quality` and `make test` in every touched project.
- Default tests must stay offline.
- Tests requiring external services must be marked `integration`.

## Fred Runtime Topology

Canonical source:

- [`docs/PLATFORM_RUNTIME_MAP.md`](../docs/PLATFORM_RUNTIME_MAP.md)
