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
- Assume no third-party services are running for default validation (no MinIO/OpenSearch/Postgres/Keycloak/OpenFGA/Temporal, etc.).
- Every new or modified function must explain:
  - why it exists
  - how to use it
  - and include a short usage example for shared/public helper functions.
- Avoid conceptual/design-pattern explanation docs; write concrete operational docs developers can apply immediately.
- Keep function count and helper layers under control: business function or strictly necessary shared helper only.
- Prefer changes that shrink and simplify the codebase (reuse/remove) instead of growing parallel logic.

## Fred Runtime Topology

Canonical source:

- [`docs/PLATFORM_RUNTIME_MAP.md`](../docs/PLATFORM_RUNTIME_MAP.md)
