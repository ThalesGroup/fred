# docs/CONVENTIONS.md

Coding style, typing, and testing rules for this repository. Applies to all
contributors and AI assistants. Source of truth for `CLAUDE.md §Step 4`.

---

## General

- **Minimal scope.** Implement exactly what the task requires. No refactors, no
  "while I'm here" cleanups, no abstraction for hypothetical future use.
- **Shared code first.** Before writing a new utility, check whether it exists in
  `fred-core`, `fred-sdk`, or the shared frontend design system. Duplicate code is
  a defect.
- **Fewer lines over more lines.** If two approaches produce the same result, choose
  the shorter one.
- **No new architecture.** Do not invent a new endpoint family, service boundary, or
  migration direction without an RFC (see `docs/swift/rfc/`).
- **No over-engineering.** No factory for a single implementation, no plugin system
  for a single case. Three similar lines is correct; premature abstraction is a bug.

---

## Python

- **Pydantic models for all public contracts.** Request bodies, response bodies,
  config schemas: always `BaseModel`. Never raw `dict` or `TypedDict` at a service
  boundary.
- **No Pydantic for internal dataclasses.** Use `@dataclass` or plain classes for
  structures that never cross an HTTP or serialisation boundary.
- **No mutable default arguments.** No `def f(x=[])`. Use `Field(default_factory=...)`
  in Pydantic, `field(default_factory=...)` in dataclasses.
- **Type-annotate every function signature.** Return type included. `Any` is allowed
  only when the upstream contract forces it — document why.
- **No silent `except Exception`.** Catch specific exceptions. When a broad catch is
  genuinely needed, log and re-raise or return an explicit error value.
- **Use existing `fred-core` utilities.** `ThreadSafeLRUCache`, `read_env_bool`,
  `get_config`, logging setup — do not reimplement.
- **Never hand-edit generated files.** `openapi.json` — regenerate from source and
  document the regeneration command when you run it.

### Testing (Python)

- **Tests offline by default.** All tests in `tests/` run without network, database,
  or external service. Tests requiring external dependencies are marked
  `@pytest.mark.integration` and excluded from `make test`.
- **One test file per module.** `tests/test_<module>.py` mirrors `package/<module>.py`.
  Do not pile unrelated tests into a single file.
- **`make code-quality && make test` must pass** before reporting any task done.

---

## Frontend (TypeScript / React)

- **Design system tokens only.** No hardcoded colours, sizes, or spacing. No
  `var(--token, fallback)` with colour or dimension fallbacks — add the missing token
  to the token file instead.
- **Every `background` has an explicit `color`.** Colour and background are always paired.
- **CSS modules only.** No inline styles, no `styled-components`, no MUI `sx` prop
  in rework components.
- **No MUI in `src/rework/`.** Use design system atoms (`Button`, `Icon`,
  `IconButton`, `Switch`, `TextInput`, `TextArea`, `ButtonGroup`, `Select`). If an
  atom is missing, add it — do not pull in MUI.
- **Strict icon typing.** Icon names must be in `MaterialIconType` (`Type.ts`). Add
  the name to the union rather than widening to `string`.
- **No `any` at component boundaries.** Props interfaces are typed. Internal state
  can use `unknown` with a guard; never `as any` at a prop or hook boundary.
- **Never hand-edit generated slices.** `runtimeOpenApi.ts`, `controlPlaneOpenApi.ts`,
  `knowledgeFlowOpenApi.ts` — regenerate from OpenAPI spec.
- **`tsc --noEmit` and Prettier must pass** before reporting any frontend task done.
  For files under `apps/frontend/src/rework/`, also read
  `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md`.
