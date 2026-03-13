# AGENTS.md

All coding assistants working in this repository must follow:

- [`docs/DEVELOPER_CONTRACT.md`](./docs/DEVELOPER_CONTRACT.md)
- [`docs/PLATFORM_RUNTIME_MAP.md`](./docs/PLATFORM_RUNTIME_MAP.md)

Mandatory defaults:

- Keep changes minimal and avoid over-engineering.
- Run `make code-quality` and `make test` in every touched project.
- Keep default tests offline (no external service dependency).
- Mark external-service tests as `integration`.
