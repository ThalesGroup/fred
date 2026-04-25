# Control Plane CLI Backlog

## 0 Overview

### 0.1 Goal

Introduce a first-class developer/operator CLI for `control-plane-backend`
that plays the same role for product/admin flows as `fred-agent-chat` already
plays for runtime execution flows.

This CLI must let one developer inspect and manage the control-plane surface
from a real terminal session, without depending on the frontend and without
copying `fred-runtime` CLI code into another backend.

Typical target use cases:

- inspect frontend bootstrap and active product surface
- list teams, templates, managed instances, and sessions
- enroll / unenroll one managed agent instance
- inspect one runtime binding
- prepare one execution context for manual validation
- inspect purge policy resolution and trigger one manual lifecycle run

---

### 0.2 Why This Matters

Today Fred has a strong runtime validation client (`fred-agent-chat`) but no
equivalent operator console for `control-plane-backend`.

This creates a blind spot:

- the runtime is easy to validate without the frontend
- the control-plane product surface is not
- developers fall back to Swagger, ad hoc `curl`, or frontend behavior to
  understand managed-agent lifecycle

For the next migration steps, this gap becomes too expensive:

- `control-plane-backend` is now the sole authority for managed agent
  enrollment, runtime discovery, session metadata, and execution preparation
- these flows need a stable, explicit CLI consumer
- this CLI should become the easiest way to debug control-plane state during
  migration and operations

---

### 0.3 Core Decision

Do **not** clone `fred-agent-chat` into `control-plane-backend`.

Instead:

1. keep runtime-specific chat behavior in `fred-runtime`
2. move only truly shared CLI infrastructure into `fred-core`
3. implement control-plane-specific commands inside
   `control-plane-backend`

This preserves the architecture rule:

- `fred-runtime` owns execution concerns
- `control-plane-backend` owns product/admin concerns
- `fred-core` owns only minimal, stable shared primitives

---

### 0.4 Current Implementation Status (2026-04-25)

The core implementation for this backlog is now in place.

Shipped pieces:

- shared CLI/auth/bootstrap primitives extracted to `fred-core`
- `fred-agent-chat` refit to consume those shared helpers
- dedicated `fred-control-plane-cli` console script added in
  `control-plane-backend`
- `make cli` added in `apps/control-plane-backend/Makefile`
- typed control-plane HTTP client added for product/admin API consumption
- MVP command surface added for bootstrap, teams, templates, instances,
  enrollment, unbind, runtime binding, sessions, prepare-execution, policy, and
  lifecycle inspection
- offline validation completed with `make code-quality` and `make test` in:
  - `control-plane-backend`
  - `libs/fred-core`
  - `libs/fred-runtime`

Remaining work before this backlog is considered fully closed:

- live validation in a real no-security setup
- live validation in a real Keycloak-enabled setup
- one operator happy path for enroll / unbind / prepare-execution against a
  running stack

---

## 1 Design Rules

### 1.1 What Belongs In `fred-core`

Only the generic CLI building blocks that are useful across multiple Fred
backends:

- `ENV_FILE` / `CONFIG_FILE` resolution aligned with backend startup
- YAML-assisted auth discovery
- Keycloak user session cache / refresh / logout helpers
- bearer-token provider helpers
- small HTTP client helpers
- optional tiny REPL helpers that know nothing about runtime chat semantics

These shared pieces must stay backend-agnostic.

They must not assume:

- runtime SSE
- agent execution events
- checkpoint semantics
- control-plane-specific endpoints
- knowledge-flow-specific resources

---

### 1.2 What Must Stay In `fred-runtime`

`fred-runtime` keeps everything that is specific to runtime execution:

- `fred-agent-chat`
- agent selection and one-shot chat execution
- runtime SSE rendering
- checkpoint/history inspection commands tied to runtime contracts
- scenario execution against runtime pods
- runtime KPI-oriented commands that depend on runtime metrics conventions

The runtime CLI remains a first-class contract consumer for execution.
It must not become the generic home for all Fred CLIs.

---

### 1.3 What Belongs In `control-plane-backend`

The control-plane CLI should own only control-plane behavior:

- parser / entrypoint for the control-plane console
- typed API client for control-plane endpoints
- control-plane slash-commands or subcommands
- rendering of team/template/instance/session/product data
- operator workflows around enrollment, runtime binding, and policy/lifecycle

The local developer entrypoint should be exposed as:

- one dedicated console script
- one `make cli` target in `control-plane-backend`

---

### 1.4 What Is Explicitly Deferred

Do **not** implement a `knowledge-flow-backend` CLI in this phase.

That work is intentionally deferred until:

1. `knowledge-flow-backend` is moved under `apps/`
2. its app packaging and startup ergonomics are aligned with `fred-agents`
3. we can design a KF console around the final app shape, not the current repo
   layout

This backlog covers `control-plane-backend` only.

---

## 2 MVP Scope

### 2.1 Required First Commands

The first useful `control-plane` CLI must support at least:

- `whoami`
- `bootstrap`
- `teams`
- `team <team_id>`
- `templates <team_id>`
- `instances <team_id>`
- `enroll <team_id> <template_id>`
- `unbind <team_id> <agent_instance_id>`
- `runtime <agent_instance_id>`
- `sessions <team_id>`
- `prepare <team_id> <agent_instance_id>`
- `policy summary`
- `policy resolve ...`
- `lifecycle run-once ...`

Exact command spelling can evolve, but this operator workflow must be possible
from the CLI without the frontend.

---

### 2.2 Non-Goals For MVP

The first version must **not** try to become:

- an LLM-driven admin shell
- a frontend replacement
- a universal CLI for every backend
- a workflow engine
- a generic Kubernetes operations tool

It is a typed operator/developer console for the existing control-plane API.

---

## 3 Implementation Plan

### 3.0 Can This Be Done Reliably In One Pass?

Yes, but only if the scope stays intentionally narrow.

One reliable pass means:

1. extract only the minimal shared CLI primitives from `fred-agent-chat`
2. add one real `control-plane` CLI entrypoint
3. deliver the MVP commands listed in this backlog
4. validate the result with offline tests plus local no-security usage

One reliable pass does **not** mean:

- redesigning all CLI ergonomics for all backends
- introducing a generic plugin framework
- implementing the `knowledge-flow` CLI now
- rebuilding `fred-agent-chat`

The implementation should be treated as one focused backend ergonomics slice,
not as a platform-wide CLI rewrite.

---

### 3.0.1 Concrete Work To Do

The real work breaks down into four technical blocks.

#### A. Carve Out Shared CLI Support In `fred-core`

Move only the backend-agnostic pieces currently trapped inside
`fred-runtime.client`:

- env/config bootstrap helpers
- YAML-based auth discovery
- Keycloak user-session persistence and refresh
- bearer-token provider construction
- tiny HTTP client helpers

Expected touched area:

- `libs/fred-core/fred_core/common/`
- or one new focused `libs/fred-core/fred_core/cli/` package
- `libs/fred-runtime/fred_runtime/client.py` to switch to the shared helpers

Hard rule:

- shared code must not import runtime SSE contracts or runtime-specific models

#### B. Add One Control-Plane API Client

Implement a small typed client dedicated to the existing control-plane HTTP
surface:

- bootstrap
- teams
- templates
- instances
- runtime binding
- sessions
- prepare-execution
- policy endpoints
- lifecycle trigger endpoint

Expected touched area:

- `apps/control-plane-backend/control_plane_backend/`
- preferably one dedicated `cli_client.py` or similarly explicit module

Hard rule:

- the CLI calls the public control-plane API like a real consumer
- it must not reach into service-layer internals

#### C. Add One Real Control-Plane CLI

Implement the console entrypoint, parser, command handlers, and rendering:

- one console script in `apps/control-plane-backend/pyproject.toml`
- one `make cli` target in `apps/control-plane-backend/Makefile`
- one command module or small command package
- stable terminal rendering for JSON-like admin data

Expected touched area:

- `apps/control-plane-backend/pyproject.toml`
- `apps/control-plane-backend/Makefile`
- one or a few new CLI modules under `control_plane_backend/`

Hard rule:

- keep command handling explicit and typed
- no LLM, no magic natural-language shell

#### D. Validate Without Frontend Dependencies

Add tests and local validation for:

- no-security startup
- auth discovery
- command-to-endpoint mapping
- enrollment / unbind happy path
- prepare-execution inspection
- policy and lifecycle commands

Expected touched area:

- `apps/control-plane-backend/tests/`
- `libs/fred-core` tests if shared auth/CLI helpers move there
- `libs/fred-runtime` tests if helper extraction changes `fred-agent-chat`

---

### 3.0.2 Recommended File-Level Shape

To keep the change solid and understandable, the implementation should stay
close to this shape:

- `fred-core`
  - tiny shared CLI/auth/bootstrap helpers only
- `fred-runtime`
  - `fred-agent-chat` updated to consume those helpers
- `control-plane-backend`
  - `control_plane_backend/cli.py` for entrypoint
  - `control_plane_backend/cli_client.py` for typed HTTP calls
  - `control_plane_backend/cli_rendering.py` if output formatting needs a
    separate small module
  - `Makefile` target `make cli`
  - console script in `pyproject.toml`

Avoid creating many layers beyond that unless duplication becomes real.

---

### 3.1 Phase A — Extract Minimal Shared CLI Primitives

- [x] Identify the generic pieces currently embedded in `fred-agent-chat`
- [x] Move only the reusable pieces to `fred-core`
- [x] Keep the extraction intentionally small
- [x] Ensure `fred-agent-chat` still works after the extraction

Success rule:

- no `control-plane-backend -> fred-runtime` dependency is introduced

---

### 3.2 Phase B — Add Control-Plane CLI Entry Point

- [x] Add one console script for the control-plane CLI
- [x] Add `make cli` in `control-plane-backend`
- [x] Reuse the same `ENV_FILE` / `CONFIG_FILE` startup convention as the API
- [x] Reuse the same Keycloak discovery rules as the backend config
- [x] Allow operation in both security-enabled and no-security local modes

---

### 3.3 Phase C — Deliver MVP Control-Plane Commands

- [x] Add typed commands for bootstrap, teams, templates, instances, sessions
- [x] Add enroll / unbind flows
- [x] Add runtime binding inspection
- [x] Add execution preparation inspection
- [x] Add purge-policy and lifecycle commands

Success rule:

- one developer can validate managed-agent lifecycle from terminal only

---

### 3.4 Recommended Delivery Order Inside The Same Pass

If this is implemented in one pass, the safest order is:

1. extract the shared helpers to `fred-core`
2. refit `fred-agent-chat` to prove the extraction is sound
3. add the control-plane typed HTTP client
4. add the control-plane CLI entrypoint and `make cli`
5. add the read-only commands first
6. add the write commands (`enroll`, `unbind`, `lifecycle run-once`)
7. run project validations

This order minimizes risk because it proves the shared helper extraction before
adding the new CLI behavior on top.

---

## 4 Validation

### 4.1 Functional Validation

Offline and project-local validation is complete. The environment-backed checks
below are the remaining closeout items for this backlog.

- [x] `make cli` starts from `control-plane-backend`
- [x] CLI resolves auth/config from the same files as backend startup
- [x] offline/unit validation is green in `control-plane-backend`,
      `libs/fred-core`, and `libs/fred-runtime`
- [ ] CLI works when security is disabled
- [ ] CLI works with Keycloak login when security is enabled
- [ ] one developer can enroll and unbind an agent instance without Swagger
- [ ] one developer can prepare execution and inspect the resulting runtime URL
      and grant scope without the frontend

---

### 4.2 Architecture Validation

- [x] Shared generic code lives in `fred-core`
- [x] Runtime-specific chat logic stays in `fred-runtime`
- [x] Control-plane-specific command logic stays in `control-plane-backend`
- [x] No `knowledge-flow-backend` CLI is started in this phase

---

### 4.3 Definition Of "Solid And Reliable"

This backlog should be considered done only if all of the following are true:

- `fred-agent-chat` still works after shared helper extraction
- the new control-plane CLI works from `make cli`
- the CLI remains useful in both no-security and Keycloak-enabled setups
- the implementation introduces no dependency from `control-plane-backend` to
  `fred-runtime`
- the command surface is small, explicit, and understandable to one developer
  reading the code later
- `knowledge-flow` remains out of scope for this pass

---

## 5 Follow-Up After This Backlog

After this backlog is implemented and validated:

1. keep `fred-agent-chat` as the runtime validation console
2. use the new control-plane CLI as the product/admin validation console
3. only then reopen the `knowledge-flow` CLI topic

The `knowledge-flow` CLI must be discussed explicitly in a later phase, after
`knowledge-flow-backend` has been moved under `apps/` and treated as an app
similar in shape to `fred-agents`.
