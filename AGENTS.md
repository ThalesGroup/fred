# AGENTS.md

All coding assistants working in this repository must follow:

- [`docs/DEVELOPER_CONTRACT.md`](./docs/DEVELOPER_CONTRACT.md)
- [`docs/PLATFORM_RUNTIME_MAP.md`](./docs/PLATFORM_RUNTIME_MAP.md)

Mandatory defaults:

- Keep changes minimal and avoid over-engineering.
- Run `make code-quality` and `make test` in every touched project.
- Keep default tests offline (no external service dependency).
- Mark external-service tests as `integration`.
- For all default validation, assume zero third-party services are running (no MinIO, OpenSearch, Postgres, Keycloak, OpenFGA, Temporal, etc.).
- Every new/modified function must document:
  - why it exists
  - how to use it
  - and include a short usage example for shared helpers/public utility functions.
- Keep functions intentional: business function or necessary shared helper that removes duplication.
- For each new feature/improvement, prefer codebase shrink/reuse/refactor over net code growth.
