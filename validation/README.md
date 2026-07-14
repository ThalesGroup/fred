# `validation/` - black-box validation of a running Fred platform

This is **not** a test of the deployment-factory itself. It is a small pytest app,
now living inside the `fred` monorepo itself (`validation/`, a sibling of `apps/`
and `libs/`), that logs in **as the real users** defined in
[`../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json`](../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json)
(alice, bob, phil, ...) and asserts the **authorization matrix** expected by the
no-grant runtime authorization model.

The current supported mode is **localhost auth/isolation validation**: backing
services run in Docker (Keycloak, Postgres, OpenFGA, OpenSearch, Temporal, ...),
while the Fred applications run in the foreground from this `fred` checkout
(`apps/control-plane-backend`, `apps/fred-agents`, `apps/knowledge-flow`,
`apps/frontend`) using their `configuration_prod.yaml`.

It reads the user/role/team matrix straight from that fixture, so there is **no
drift**: change the users there and the assertions follow. That same fixture is
also the checked-in source for `make build-demo-bundle` (in
`apps/control-plane-backend`), the zip an operator uploads via Admin > Migration
to actually provision the users/teams/roles this suite expects to find.

On a fresh Swift stack, the suite **verifies** (never provisions) the
collaborative teams and roles before running assertions: it reads each team
through the real Control Plane APIs (as the configured `platform_admin` and, per
team, the configured `team_admin`) and fails fast with an actionable message -
pointing at `make build-demo-bundle` + the Admin > Migration upload - if anything
expected is missing. Team **and identity** provisioning is owned by
control-plane's platform-import feature (see `PLATFORM-IMPORT-RFC.md` Part A),
not by this suite; `make docker-up` only prepares empty Keycloak/OpenFGA infra.

## Why it exists

RBAC/ReBAC is per-identity and complex. Testing it by hand from the UI is a
non-starter (a browser is one identity at a time). This driver holds **many
identities** and checks who can do what - the honest way to validate ReBAC.

## Why these exact users

Every user in the `demo_provisioning` fixture exists to prove one specific, real
claim about who can see what in the clean Swift model:

- **alice** - `platform_admin` only → proves a platform admin is a platform actor,
  not an implicit member/admin of every team.
- **gabriel** - `platform_observer` only → same isolation proof for the read-only
  platform role.
- **bob / derek** - `team_editor` fixtures → can work in their assigned teams and
  cannot cross into unassigned teams.
- **sophia / marc / nadia** - `team_admin` fixtures → one admin per collaborative
  team, used for legitimate team-admin workflows without platform escalation.
- **phil / zoe / liam** - plain `team_member` fixtures → ordinary member visibility
  and runtime access.
- **elena** - `team_analyst` of `fredlab` only, and no other role → dedicated persona
  for evaluation-campaign capabilities (`can_run_evaluations`,
  `can_manage_evaluation_corpus`, `can_read_conversations_for_evaluation`), isolated
  from admin/editor capabilities.
- **priya** - `team_admin` + `team_editor` + `team_analyst` on `fredlab` at once
  (AUTHZ-06 cumulative roles, RFC Part 7 §33-39) → proves the cumulative case gets the
  union of every role's capabilities; see `scenarios/test_cumulative_team_roles.py`.
- **oscar / nina / quinn** - identity-only controls → authenticated users
  with no OpenFGA grant get no collaborative team data by default.

If you need to add a user later, ask first: *what specific claim does this
person prove or disprove that no existing user already covers?* If there isn't
a one-sentence answer, it's noise, not signal.

## Supported validation modes

### Current mode - localhost auth/isolation

This is the current black-box release-validation mode.

1. Start the deployment-factory Docker infrastructure: Keycloak, Postgres,
   OpenFGA, OpenSearch, Temporal and the other backing services.
2. Start the Fred applications manually from the `swift` checkout, in separate
   terminals, using their `configuration_prod.yaml`:
   - `apps/control-plane-backend`
   - `apps/fred-agents`
   - `apps/knowledge-flow` / worker if the tested flow needs it
   - `apps/frontend` if you want to validate the browser-facing proxy path
3. Point `FRED_CONTROL_PLANE_URL` at the manually started control-plane, usually
   `http://localhost:8222/control-plane/v1`.
4. Point runtime calls at the same public base that a browser would use for the
   `execute_stream_url` returned by `prepare-execution`. In the current direct
   runtime setup, that is usually the manually started `fred-agents` server, not
   the control-plane port.

Important: `prepare-execution` returns ingress-relative URLs such as
`/fred/agents/v2/agents/execute/stream`. Those URLs are **not** served by the
control-plane itself. If `FRED_CONTROL_PLANE_URL` is `http://localhost:8222`,
calling `http://localhost:8222/fred/agents/v2/...` is expected to return `404`.
That is a harness/routing configuration issue, not by itself a runtime authz
failure.

### Mode B - browser/proxy path

When the frontend nginx/Vite proxy is running and exposes both `/control-plane/...`
and `/fred/agents/v2/...`, the validation can target the same public origin as
the browser. This is closer to the UI path, but it also tests the proxy routing in
addition to runtime authorization.

### Mode C - future full k3d validation

`make validate-auth-isolation-k3d` is reserved for a future mode. It will deploy
Keycloak/backing services and all Fred apps inside k3d, then run the same
black-box suite against the k3d ingress. That is the right direction for a more
deployment-representative C3 evidence path, but it is explicitly **not** required
for the current revamp validation. Track it as a follow-up task, not as a blocker
for this harness.

## Prerequisites

1. **Running backing services and Fred apps** according to one of the modes above.
   Keycloak and the control-plane database must be seeded with the
   `demo_provisioning` fixture's users/teams/roles (`make build-demo-bundle` +
   Admin > Migration upload - see the intro above).
2. **Direct-grant on the `app` Keycloak client** (test realm only). The validation
   logs users in with the *password grant*; the `app` client must allow it.
   In the realm template (`docker/keycloak/app-realm.json.template`), the
   `app` client must have:
   ```json
   "directAccessGrantsEnabled" : true
   ```
   Then re-import the realm (restart Keycloak / re-run the keycloak post-install).
   **Test/dev only** - do NOT enable ROPC on a real integration / C3 realm.
3. **No grant signing requirement.** This suite targets RUNTIME-07 rev. 2: the
   control-plane does not issue `ExecutionGrant`; runtime pods validate the user
   JWT and perform pod-side OpenFGA checks.

## Configuration (env vars, with local defaults)

| Var | Default | Meaning |
|---|---|---|
| `FRED_REALM_URL` | `http://localhost:8080/realms/app` | Keycloak realm URL |
| `FRED_CLIENT_ID` | `app` | Public client used for the password grant |
| `FRED_USER_PASSWORD` | `Azerty123_` | Fallback password, used only for a user the fixture has no per-user password for (each of the 15 fixture users normally carries its own `password` field - see `factory_config.FactoryUser.password`) |
| `FRED_CONTROL_PLANE_URL` | `http://localhost:8222/control-plane/v1` | Control-plane API base. In localhost auth/isolation mode this is the direct control-plane app, not the runtime/frontend origin. |
| `FRED_RUNTIME_PUBLIC_BASE` | `http://localhost:8000` via `make validate-auth-isolation-localhost` | Public origin used to resolve ingress-relative runtime URLs returned by `prepare-execution`, e.g. direct `fred-agents` or the frontend origin for proxy-path validation. |
| `FRED_CONFIG_PATH` | `../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json` | Source of truth for users/roles |
| `FRED_TEST_TEAM` | `fredlab` | Collaborative team used for isolation checks |
| `FRED_TEST_AGENT_ID` | `fred.github.test_assistant` | Public no-LLM agent used for deterministic runtime execution |
| `FRED_KNOWLEDGE_FLOW_URL` | `http://localhost:8111/knowledge-flow/v1` | knowledge-flow-backend base, started manually like the other apps. Only required by `test_content_scope_bypass.py`; checked lazily, not at session start. |

## The complete-matrix demo users

The `demo_provisioning` fixture now covers every cell of the AUTHZ-05 role matrix
that can actually be observed against a running stack, not just team-vs-team:

| user | app_roles (legacy Keycloak) | platform_roles (AUTHZ-05 target) | teams | purpose |
|---|---|---|---|---|
| alice | none | **admin** | none | clean Swift platform_admin, isolated from team data. |
| gabriel | none | **observer** | none | clean Swift platform_observer, isolated from team data. |
| bob | none | — | team_editor of northbridge/fredlab | editor fixture for the target team role vocabulary. |
| phil, zoe, liam | none | — | team_member of 1-2 teams | plain member cross-team matrix. |
| sophia, marc, nadia | none | — | team_admin of 1 team each | team-admin matrix; one of them/bob acts as the validation operator for the test team. |
| derek | none | — | team_editor of northbridge only | proves legitimate access stays team-scoped. |
| elena | none | — | team_analyst of fredlab only | evaluation-campaign capabilities, isolated from admin/editor. |
| priya | none | — | team_admin + team_editor + team_analyst of fredlab | AUTHZ-06 cumulative roles - union of all three roles' capabilities. |
| oscar, nina, quinn | none | — | none | identity-only floor/control users. |

`platform_roles` is a fixture field (`["admin"]` / `["observer"]`), granted by
control-plane's platform-import role phase as stored `platform_admin`/
`platform_observer` OpenFGA tuples on `organization:fred` - independent of
`app_roles`, exactly matching the AUTHZ-05 target model (these relations are
never derived from a Keycloak role).

Because `scenarios/test_runtime_team_isolation.py`'s existing checks already
parametrize over every user in `USERS`, adding a user to the fixture alone
extends ~25 existing test cases for free (e.g. each new user's `/teams`
visibility and personal-space enrollment get checked automatically) - see
`test_platform_role_isolation.py` and `test_content_scope_bypass.py` for the
scenarios that specifically needed them.

## Keeping the OpenFGA model in sync

`docker/openfga/openfga-model.json` and `k3d/files/openfga/openfga-model.json`
are **hand-maintained copies** owned by `fred-deployment-factory` (not `fred`,
and not this `validation/` package since its relocation into the `fred`
monorepo) - not generated from `fred-core` directly. On 2026-07-09 the Docker
copy was found to have drifted significantly from `fred-core`'s actual
`schema.fga` - missing most organization capabilities, missing
`can_read_conversations`, and (fortunately, by omission) missing a live
escalation bug that existed in `fred` at the time. On 2026-07-13 the Helm copy
was found to have drifted too (`can_observe_platform`/`platform_observer` vs a
stale `can_read_kpi_global`/`platform_admin` shape). Both are now synced and
covered by a static guard - `make sync-openfga-model` /
`make check-openfga-model-sync`, run from `fred-deployment-factory`'s own
Makefile (see that repo's `Makefile` and `README.md`), not from here.

## Run

From **this directory** (`fred/validation`), or from the `fred` repo root via
`make -C validation validation-report` / `make validation-report`: creates
`validation/.venv` with `python3 -m venv`, installs deps incl. local-editable
`fred-core`, `fred-sdk`, and `fred-runtime` (now plain repo-sibling paths under
`../libs/`), then runs the `scenarios/` suite (no `-x` - one failure does not
hide the rest) and writes a short claims-grouped report:

```bash
make validation-report
```

The target defaults to:

```text
FRED_CONTROL_PLANE_URL=http://localhost:8222/control-plane/v1
FRED_RUNTIME_PUBLIC_BASE=http://localhost:8000
FRED_KNOWLEDGE_FLOW_URL=http://localhost:8111/knowledge-flow/v1
```

Override `FRED_RUNTIME_PUBLIC_BASE` with the frontend/proxy origin when the goal is
to validate the exact browser-facing route. Offline unit tests for the harness
itself (no running stack) are a separate target: `make validation-unit-tests`
(see below).

### A short, readable report instead of raw pytest output

`make validation-report` (above) writes `validation/report.md` and returns
pytest's exit code. That means the report is always produced for diagnosis, but
the Make target still fails when the running stack is not authorization-ready.

The report groups results by the real-world **claim** each test proves (not by
test function name), with a one-line verdict and details for failures. Example
shape:

```markdown
# Fred Authorization Validation Report

**Result:** NOT READY - 2 blocking finding(s) need attention
**Totals:** 77 passed, 1 failed, 1 error, 0 known gap (xfail), 0 possible infra issue, 0 skipped

## Platform-role isolation (AUTHZ-05)

| Result | Claim |
|---|---|
| PASS | alice holds only a platform role and sees zero collaborative teams. |
| PASS | gabriel holds only a platform role and cannot read fredlab's catalog. |

## Content-scope team isolation

| Result | Claim |
|---|---|
| PASS | Corpus capabilities requires an explicit team_id instead of falling back to organization scope. |
| PASS | A platform-only user cannot read a collaborative team's corpus capabilities. [username=alice] |
```

This is the minimal version of the tag-bound evidence report already specced in
`RFC-C3-validation-extensions.md` (Extension F) - grouping and a verdict, nothing
more. Attaching it to a git tag/commit with signed, retained artifacts
(`pytest.xml`, `environment.json`, checksums) is future work, not done here.

## What it checks

- **Identity + ReBAC membership**: each user sees exactly their teams.
- **Catalog premise**: the chosen public test agent is visible in the team catalog.
- **prepare-execution isolation**: a team member can prepare runtime execution; a
  non-member is denied; the response contains no `execution_grant`.
- **Runtime pod-side authorization**: a member can call the SSE runtime stream with
  a Keycloak JWT; a non-member cannot bypass the control-plane by calling the pod
  directly with another user's `team_id`.
- **Identity hardening**: a forged `runtime_context.user_id` does not become the
  runtime identity.
- **Enrollment authorization**: a plain member cannot enroll an agent in a
  collaborative team; a user can enroll in their own personal space.
- **Swift split-role authorization**: `team_admin` without `team_editor` cannot
  enroll agents; `team_editor` without `team_admin` cannot administer members.
- **Platform-role isolation**: `platform_admin` (`alice`) and `platform_observer`
  (`gabriel`) grant platform authority only; they do not grant collaborative team
  visibility or team content access.
- **Content-scope team isolation**: knowledge-flow `corpus/capabilities` requires
  an explicit `team_id`; members of that team are allowed, platform-only users and
  members of other teams are denied. Requires knowledge-flow-backend running (see
  `FRED_KNOWLEDGE_FLOW_URL` above).
- **AUTHZ-06 cumulative team roles** (`scenarios/test_cumulative_team_roles.py`):
  marc/bob/elena each hold exactly one of `team_admin`/`team_editor`/`team_analyst` on
  `fredlab` and only that role's capabilities; priya holds all three at once and gets
  their union, including exercising a genuine admin-gated operation (add/remove a member)
  and editor-gated operation (create/delete a prompt) through her cumulative grant.
- **Team-registry governance** (`scenarios/test_team_registry_authz.py`): team
  bootstrap/list-all/delete/rescue-admin are platform-admin-only, registry-scoped
  capabilities independent of any relation on the team itself; the last-`team_admin`
  guard applies to the granular role-revoke endpoint symmetrically with full removal.

Offline unit tests for the harness itself (`factory_config.py`'s role-resolution logic -
simple role, cumulative role, the `teams[]` -> `team_member` fallback, admin/editor/analyst
distinction, a neutral identity with no role) live in `tests/`, not `scenarios/`, and need no
running stack: `make validation-unit-tests`.
