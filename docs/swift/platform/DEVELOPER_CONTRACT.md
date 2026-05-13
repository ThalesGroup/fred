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

## 2) Platform CLI Convention

**Every Fred backend exposes `make cli`** — the primary tool for validating and operating the service from a terminal.

- Use `make cli` to validate a backend change before frontend integration.
- Any phase gate that says "backend is ready" must be reachable from `make cli`.
- Full specification: [`CLI-CONVENTION.md`](./CLI-CONVENTION.md)

## 3) Frontend Work

Read [`FRONTEND_CODING_GUIDELINES.md`](./FRONTEND_CODING_GUIDELINES.md) before touching any `.tsx`, `.css`, or `.scss` file under `src/rework/`. Key rules that have caused production bugs:

- Never use hardcoded color values (`rgba`, `#hex`) in CSS modules — use tokens only.
- Never use `var(token, #fallback)` — fallbacks mask missing tokens silently.
- Every component with its own background must set `color` explicitly using the M3 pairing rule.
- Verify a token exists in the token files before using it. If missing, add it.
- No experimental browser APIs (`CSS Anchor Positioning`, `popover` on `<div>`) as the primary implementation path.

## 4) Non-Negotiable Engineering Rules

- Keep changes minimal and direct.
  - Do not redesign unrelated parts.
  - Do not introduce abstractions without a clear immediate need.
- Every new feature should reduce complexity, not increase it.
  - Prefer deleting/replacing duplicated code over adding parallel logic.
  - If code is added, remove obsolete code in the same change whenever possible.
  - When touching shared runtime/SDK seams, prefer collapsing transitional
    bridges or duplicate request/state models instead of threading one more
    field through every copy.
  - Do not solve a cross-cutting problem with a use-case-specific side channel
    if one existing typed contract can be strengthened instead.
- Respect existing Fred conventions.
  - Same environment variable names and startup behavior across backends.
  - Same Make targets and expected developer workflow.
- Keep code strongly typed end-to-end.
  - Prefer explicit types (`Enum`/`Literal`/typed models) over magic strings.
  - Shared runtime choices (like scheduler backends) must use one typed definition from `fred_core`, not duplicated string literals.
  - `Any` and `dict[str, Any]` are not acceptable at contract, service, CLI, or persistence boundaries. If an external payload is genuinely opaque, keep it local to the adapter and mark it with a short `# opaque` or `# open bag` comment.
  - If a package uses a `basedpyright` baseline, do not treat the baseline as proof the package is type-clean. Run raw `basedpyright` as well and report whether the baseline still masks errors in the touched area.
- Keep logging uniform.
  - Reuse the existing logger families and channel split already documented for the component.
  - Prefer deferred formatting (`logger.info("...", value)`) over eager f-strings in log calls.
  - Avoid one-off prefixes or ad hoc log shapes when a component already has a visible convention.
- Keep module size intentional.
  - If a file is already very large (around `600+` lines), do not add another concern to it without extracting a focused module first or in the same change.
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
  - When a touched Python project has a non-empty `basedpyright` baseline, also run raw `basedpyright` and include the result in the close-out / PR notes.

## 3) Expected Test Behavior

- `make test`: offline/default test suite only (CI baseline).
- `make test-integration` (or equivalent): external-service tests only.

Example:

- If a test downloads models from internet or needs running services, it is an integration test.
- If a test can run from a clean laptop with no services started, it belongs to default `make test`.

## 5) Required PR Checks

Each PR must explicitly confirm:

- Scope kept minimal (no over-engineering).
- `make code-quality` executed on touched projects.
- `make test` executed on touched projects.
- Raw `basedpyright` executed for any touched package that keeps a non-empty baseline file, with the result stated explicitly.
- New external dependency tests marked as integration.
- Documentation updated when behavior/rules changed.

## 6) AI Assistant Instructions

When prompting an assistant, start with:

`Follow docs/DEVELOPER_CONTRACT.md strictly.`

Short prompt template:

`Read docs/DEVELOPER_CONTRACT.md first. Keep changes minimal, keep default tests fully offline (no third-party services), document each changed function with why/how (example for shared helpers), avoid new Any/dict[str, Any] at boundaries, run raw basedpyright when a baseline exists, and prefer shrinking/reusing code instead of growing it.`
