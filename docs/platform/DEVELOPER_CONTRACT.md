# Developer Contract (Humans + AI Assistants)

This document defines the mandatory working rules for this repository.

If you use an AI assistant in VS Code (Codex, Claude, Copilot, Gemini), this is the reference it must follow first.

## 1) Read Order Before Any Code Change

Read these files in this order:

1. [`README.md`](../README.md)
2. [`docs/PLATFORM_RUNTIME_MAP.md`](./PLATFORM_RUNTIME_MAP.md)
3. [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./CONFIGURATION_AND_POLICY_CONVENTIONS.md)
4. [`docs/REBAC.md`](./REBAC.md) for access-control related work
5. [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md)

## 2) Non-Negotiable Engineering Rules

- Keep changes minimal and direct.
  - Do not redesign unrelated parts.
  - Do not introduce abstractions without a clear immediate need.
- Every new feature should reduce complexity, not increase it.
  - Prefer deleting/replacing duplicated code over adding parallel logic.
  - If code is added, remove obsolete code in the same change whenever possible.
- Respect existing Fred conventions.
  - Same environment variable names and startup behavior across backends.
  - Same Make targets and expected developer workflow.
- Keep code strongly typed end-to-end.
  - Prefer explicit types (`Enum`/`Literal`/typed models) over magic strings.
  - Shared runtime choices (like scheduler backends) must use one typed definition from `fred_core`, not duplicated string literals.
- Keep unit tests infrastructure-free.
  - Unit/default tests must not require Docker or external services.
  - No dependency on running Keycloak, Temporal, OpenFGA, MinIO, Postgres, etc.
  - Tests needing external services must be marked `@pytest.mark.integration`.
- Documentation style must be developer-operational and concrete.
  - Every new or modified function must document:
    - Why it exists.
    - How to use it.
  - Prefer short usage examples for shared helpers/public utility functions.
  - Do not write conceptual or design-pattern prose that does not help direct usage.
- Function shape must stay intentional.
  - A function should be either:
    - a clear business function, or
    - a strictly necessary shared helper used to remove duplication.
  - Avoid one-off helper layering that adds indirection without reuse.
- Validate every change before proposing merge.
  - Run `make code-quality` in each modified Python project.
  - Run `make test` in each modified project.

## 3) Expected Test Behavior

- `make test`: offline/default test suite only (CI baseline).
- `make test-integration` (or equivalent): external-service tests only.

Example:

- If a test downloads models from internet or needs running services, it is an integration test.
- If a test can run from a clean laptop with no services started, it belongs to default `make test`.

## 4) Required PR Checks

Each PR must explicitly confirm:

- Scope kept minimal (no over-engineering).
- `make code-quality` executed on touched projects.
- `make test` executed on touched projects.
- New external dependency tests marked as integration.
- Documentation updated when behavior/rules changed.

## 5) AI Assistant Instructions

When prompting an assistant, start with:

`Follow docs/DEVELOPER_CONTRACT.md strictly.`

Short prompt template:

`Read docs/DEVELOPER_CONTRACT.md first. Keep changes minimal, keep default tests fully offline (no third-party services), document each changed function with why/how (example for shared helpers), and prefer shrinking/reusing code instead of growing it.`
