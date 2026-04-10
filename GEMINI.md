# GEMINI.md

For any change in this repository, follow:

- [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md)
- [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)

Minimum required behavior:

- Keep implementation minimal.
- Do not over-engineer.
- Run `make code-quality` and `make test` in touched projects.
- Keep default tests offline; mark external dependency tests as `integration`.
