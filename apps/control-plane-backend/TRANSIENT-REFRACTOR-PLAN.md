# Control Plane Backend — Transient Refactor Plan

This file is a temporary execution note for the internal architecture cleanup of
`apps/control-plane-backend`.

It is **not** a product contract, backlog source of truth, or migration spec.
It exists only to help us execute the refactor in clean, reviewable slices while
still landing the work as one final commit if we choose.

## Goal

Move `control-plane-backend` to explicit dependency injection and composition
roots, without changing public product behavior, API contracts, startup
conventions, or offline testability.

## Non-Negotiables

- Keep runtime vs control-plane boundaries unchanged.
- Keep OpenAPI contracts stable unless a real bug requires a fix.
- Keep default tests fully offline.
- Avoid framework-heavy DI; use explicit Python constructors and FastAPI
  dependencies.
- Prefer compatibility shims during migration, then remove them at the end.
- After each slice: run `make code-quality` and `make test`.

## Working Mode

We will execute this as **PR-style slices**, but may keep the work uncommitted
until the full result is ready.

That means each slice should be:

- understandable in isolation
- safe to validate independently
- reversible if needed
- small enough to debug without losing momentum

## Slice 1 — Composition Root First

**Objective**

Introduce explicit application wiring without changing business behavior.

**Scope**

- Add `control_plane_backend/app/container.py`.
- Add `control_plane_backend/app/dependencies.py`.
- Add `control_plane_backend/app/lifespan.py` if it improves clarity.
- Move startup-only registration work out of `ApplicationContext.__init__()`.
- Keep `ApplicationContext` temporarily as a compatibility shim.

**Done when**

- `main.py` and `main_worker.py` create/wire dependencies explicitly.
- No constructor side effect remains in `ApplicationContext`.
- Existing APIs and tests still pass unchanged.

## Slice 2 — Team Read/Write DI Migration

**Objective**

Make `teams/` the first feature package that no longer depends on the global
application context.

**Scope**

- Replace hidden `ApplicationContext.get_instance()` calls in `teams/service.py`.
- Introduce explicit collaborators for:
  - ReBAC
  - Keycloak group access
  - team metadata store
  - content store
  - user directory lookup
  - purge queue/session store access
  - policy catalog access
  - scheduler trigger hook
- Split the file only where it clearly reduces responsibility overlap.

**Preferred target shape**

- `teams/service.py` for primary orchestration
- `teams/keycloak_gateway.py` for Keycloak group/member operations
- `teams/assembler.py` for `Team`/`TeamWithPermissions` enrichment
- optional `teams/membership_service.py` only if the top-level module remains too broad

**Done when**

- `teams/` business functions receive their collaborators explicitly.
- `teams/` no longer imports `ApplicationContext`.
- Route handlers resolve services through FastAPI dependencies.

## Slice 3 — Product Service Split + DI

**Objective**

Turn `product/service.py` into a set of explicit product use cases with visible
collaborators.

**Scope**

Split responsibilities into focused services such as:

- frontend bootstrap
- runtime template discovery
- managed agent instance CRUD
- session metadata
- execution preparation/runtime binding

**Preferred target shape**

- `product/bootstrap_service.py`
- `product/templates_service.py`
- `product/instances_service.py`
- `product/sessions_service.py`
- `product/execution_service.py`
- `product/runtime_gateway.py`

**Done when**

- `product/` no longer reaches into `ApplicationContext`.
- Public API handlers depend on explicit product services.
- Duplicate session / runtime binding logic stays typed and locally testable.

## Slice 4 — Users + Lifecycle Edge Cleanup

**Objective**

Finish the remaining context-dependent edges.

**Scope**

- migrate `users/service.py`
- migrate `scheduler/lifecycle_actions.py`
- align any worker wiring still using `ApplicationContext.get_instance()`
- keep scheduler backend selection typed and unchanged

**Done when**

- all remaining business modules use injected collaborators
- worker bootstrap is wiring-only

## Slice 5 — Delete Global Context Pattern

**Objective**

Remove the temporary compatibility layer once all call sites are migrated.

**Scope**

- delete `ApplicationContext.get_instance()` usage
- remove `get_app_context()` and compatibility-only helpers
- reduce `app/context.py` to config-only helpers or remove it completely

**Done when**

- `rg 'ApplicationContext.get_instance' apps/control-plane-backend/control_plane_backend` returns nothing
- app wiring is fully rooted in container/dependency modules

## Slice 6 — Structure Polish

**Objective**

Leave the codebase simpler than we found it.

**Scope**

- tighten names and file boundaries
- remove dead compatibility code
- keep helper count low
- align tests with the new dependency seams
- only then revisit whether tiny shared helpers should move to `fred-core`

**Done when**

- no transitional module feels permanent-by-accident
- tests read naturally against feature services and gateways
- app startup files are small and boring

## Test Strategy Per Slice

Run after every slice:

- `make -C apps/control-plane-backend code-quality`
- `make -C apps/control-plane-backend test`

Keep external-service scenarios out of the default path.

## Suggested Execution Order For Today

1. Slice 1 — composition root and compatibility shim
2. Slice 2 — `teams/`
3. Slice 3 — `product/`
4. Slice 4 — `users/` + lifecycle edges
5. Slice 5 — remove global context
6. Slice 6 — polish only after the system is green

## Stop Conditions

Pause and realign before continuing if any slice causes:

- API contract drift
- frontend type drift not required by a bug fix
- startup convention drift (`ENV_FILE`, `CONFIG_FILE`, `make run`, `make run-worker`)
- non-offline default tests
- a bigger abstraction layer than the code actually needs
