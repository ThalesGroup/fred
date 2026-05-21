# AGENTS.md

All coding assistants working in this repository must follow:

- [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md)
- [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)

Mandatory defaults:

- Keep changes minimal and avoid over-engineering.
- Run `make code-quality` and `make test` in every touched project.
- Keep default tests offline (no external service dependency).
- Mark external-service tests as `integration`.
- For all default validation, assume zero third-party services are running (no MinIO, OpenSearch, Postgres, Keycloak, OpenFGA, Temporal, etc.).
- Document new or modified shared/public functions when useful with short, standard developer-oriented comments or docstrings.
- Prefer concise purpose/usage notes over rigid templates.
- Add a short usage example only for shared helpers when it materially helps readability.
- Keep functions intentional: business function or necessary shared helper that removes duplication.
- For each new feature/improvement, prefer codebase shrink/reuse/refactor over net code growth.
