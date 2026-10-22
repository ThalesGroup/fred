# `validation/` - black-box validation of a running Fred platform

This is **not** a test of the deployment-factory itself. It is a small pytest app,
now living inside the `fred` monorepo itself (`validation/`, a sibling of `apps/`
and `libs/`), that logs in **as the real users** defined in
[`../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json`](../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json)
(alice, bob, phil, ...) and asserts the **authorization matrix** expected by the
no-grant runtime authorization model.

The suite targets an already running deployment: local applications with Docker
backing services, or a complete k3d installation through its ingress. It does
not deploy the platform. Set the endpoints and authentication prerequisites for
the chosen environment before running it.

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
control-plane's platform-import feature (see `CONTROL-PLANE-PRODUCT-CONTRACT.md §27`),
not by this suite; `make docker-up` only prepares empty Keycloak/OpenFGA infra.

## Why it exists

RBAC/ReBAC is per-identity and complex. Testing it by hand from the UI is a
non-starter (a browser is one identity at a time). This driver holds **many
identities** and checks who can do what - the honest way to validate ReBAC.

## Why these exact users

Every user in the `demo_provisioning` fixture exists to prove one specific, real
claim about who can see what in the clean Swift model:

- **alice** - `platform_admin` only → proves a platform admin is a platform actor,
  not an implicit *member*/admin of every team (a public team may still list her
  as a non-member entry for marketplace discovery — TEAM-10, GitHub #2146 cluster
  C — what must never happen is `is_member`/content access).
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
  with no OpenFGA grant get no collaborative team *membership* or content by
  default (public teams may still appear in `/teams` for discovery, `is_member`
  stays `false` — TEAM-10, GitHub #2146 cluster C).

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

   For the full step-by-step sequence - infra up, prod-like config, AUTHZ-07
   root bootstrap, demo-data import, starting each app, then this suite and
   the Admin > Self-test UI check - see `fred-deployment-factory`'s
   `docs/LOCAL-DEVELOPMENT.md` ("Full bootstrap walkthrough").
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

### Mode C - an existing k3d deployment

Use `make integration-test-k3d` with the default k3d ingress and trusted realm
coordinates documented below. The cluster and demo import must already exist. A
command that creates the cluster and deploys the applications as part of validation
remains future work.

## Prerequisites

1. **Running backing services and Fred apps** according to one of the modes above.
   Keycloak and the control-plane database must be seeded with the
   `demo_provisioning` fixture's users/teams/roles (`make build-demo-bundle` +
   Admin > Migration upload - see the intro above).
2. **Password-grant login on the local test client.** The harness logs in as
   each demo user without a browser. This requires **Direct access grants** on
   Keycloak client `app`; a successful browser login does not prove this flow is
   enabled. See the [k3d preparation procedure](#run-against-the-existing-k3d-deployment)
   for the setting, its lifetime and failure symptoms.
3. **Test agent, document capability and model access.** Runtime scenarios need
   these enabled for the test team, independently of its users' roles. The same
   [k3d procedure](#run-against-the-existing-k3d-deployment) explains the model
   prerequisite even for **Test Assistant (no LLM)**.
4. **No grant signing requirement.** This suite targets RUNTIME-07 rev. 2: the
   control-plane does not issue `ExecutionGrant`; runtime pods validate the user
   JWT and perform pod-side OpenFGA checks.

## Configuration (env vars, with local defaults)

| Var | Default | Meaning |
|---|---|---|
| `FRED_REALM_URL` | `http://localhost:8080/realms/app` | Keycloak realm URL |
| `FRED_CLIENT_ID` | `app` | Public client used for the password grant |
| `FRED_USER_PASSWORD` | `Azerty123_` | Fallback password, used only for a user the fixture has no per-user password for (each of the 15 fixture users normally carries its own `password` field - see `factory_config.FactoryUser.password`) |
| `FRED_CONTROL_PLANE_URL` | `http://localhost:8222/control-plane/v1` | Control-plane API base. In localhost auth/isolation mode this is the direct control-plane app, not the runtime/frontend origin. |
| `FRED_RUNTIME_PUBLIC_BASE` | `http://localhost:8000` | Public origin used to resolve ingress-relative runtime URLs returned by `prepare-execution`, e.g. direct `fred-agents` or the frontend origin for proxy-path validation. |
| `FRED_CONFIG_PATH` | `../apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json` | Source of truth for users/roles |
| `FRED_TEST_TEAM` | `fredlab` | Collaborative team used for isolation checks |
| `FRED_TEST_AGENT_ID` | `fred.github.test_assistant` | Public no-LLM agent used for deterministic runtime execution |
| `FRED_KNOWLEDGE_FLOW_URL` | `http://localhost:8111/knowledge-flow/v1` | knowledge-flow-backend base, started manually like the other apps. Required by `test_document_access.py`; checked lazily, not at session start. |

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
# Docker-backed local infrastructure and running Fred apps on direct ports:
make integration-test-docker

# Existing local k3d deployment:
make integration-test-k3d
```

Both targets run the same validation suite and generate `validation/report.md`
and `validation/report.xml`. They do not start, rebuild or redeploy services,
import demo data or change Keycloak/Fred permissions. Complete the prerequisites
above before running either target.

| Target | Control Plane | Knowledge Flow | Runtime origin | Keycloak realm |
| --- | --- | --- | --- | --- |
| `integration-test-docker` | `localhost:8222/control-plane/v1` | `localhost:8111/knowledge-flow/v1` | `localhost:8000` | `localhost:8080/realms/app` |
| `integration-test-k3d` | `localhost:8088/control-plane/v1` | `localhost:8088/knowledge-flow/v1` | `localhost:8088` | `keycloak:8080/realms/app` |

All these default URLs use HTTP. A named profile replaces previously exported
endpoint variables so stale Docker ports cannot affect a k3d run. Explicit Make
command-line assignments override the profile, for example
`make integration-test-k3d FRED_RUNTIME_PUBLIC_BASE=http://localhost:9088`.
`VALIDATION_ARGS`, `VALIDATION_REPORT` and `VALIDATION_JUNIT_XML` work with either
profile. The targets are also available via `make -C validation`.

`make validation-report` remains the configurable entry point: it honors exported
`FRED_*` variables and command-line assignments. Without overrides it defaults to:

```text
FRED_REALM_URL=http://localhost:8080/realms/app
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

## Document access, revocation and conversation freshness

| Result | Claim |
|---|---|
| PASS | A personally readable B document selected by UID is excluded in active team A. [policy=semantic] |
| PASS | A second turn in the same session retrieves a document ingested after the first turn. |
```

This is the minimal version of the tag-bound evidence report already specced in
`RFC-C3-validation-extensions.md` (Extension F) - grouping and a verdict, nothing
more. Attaching it to a git tag/commit with signed, retained artifacts
(`pytest.xml`, `environment.json`, checksums) is future work, not done here.

## What it checks

- **Identity + ReBAC membership**: each user is a *member* (`is_member`) of exactly
  their own teams (public teams may still be *listed* for discovery without
  membership — TEAM-10, GitHub #2146 cluster C).
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
- **Document access and lifecycle**: real document retrieval stays within the
  active team and selected documents; unlinking a shared document revokes access;
  newly ingested documents reach an existing conversation. See the detailed
  coverage and prerequisites below.
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


## Document access and conversation changes

`scenarios/test_document_access.py` adds live checks for issue
[#3091](https://github.com/ThalesGroup/fred/issues/3091). It selects an existing
editor of two demo teams, plus an exclusive reader in each team, from `USERS`.
With the default fixture these are Bob, Zoe and Phil (the first eligible
Northbridge reader). No identities, roles or existing documents are modified.
User credentials are refreshed through the existing CLI session manager during long campaigns; its
temporary session files are removed when pytest exits.

The campaign creates uniquely named libraries, small Markdown documents,
managed diagnostic agents and sessions. Cleanup targets their returned IDs,
including when an assertion fails. It uploads real documents, waits for ingestion
tasks and initial index visibility, and exercises the configured vector backend.
A working embedding service and Knowledge Flow worker are required. The runtime
checks also require the public `fred.github.test_assistant` template and enabled
`document_access` capability. No chat LLM is used: the diagnostic agent returns
the actual search hits. The driver confirms
only its fixed `test_document_confirm` pause, preserving the same session and
selection on resume; unexpected pauses or failed tools fail the test.

Coverage includes:

- Library scope and explicit document selection across two readable teams, for
  semantic, hybrid and strict search; positive controls prove retrieval works.
- Rejected library/document selections do not widen to the authorized corpus.
- Direct metadata and chunk reads reject a reader outside the owning team.
- A single UID is indexed in two team libraries, then unlinked from one. The
  remaining team can still retrieve it; the removed team's reader must lose
  library-search, explicit-search, metadata and chunk access. Negative assertions
  are immediate after successful removal, not retried until a leak disappears.
- Runtime UID scoping and a new library document becoming retrievable on the
  next turn of the same session.
- A late chat attachment becoming retrievable in an existing session; isolation
  from other users/sessions, including when a corpus document is selected, through
  both a real runtime turn and the direct Knowledge Flow search API.

These tests assert the intended behavior without `xfail`. An affected deployment
is expected to fail the relevant assertions; these are diagnostic tests, not a
product fix. A failed positive control is a failed setup, never proof of isolation.

### Run against the existing k3d deployment

The default local factory exposes Fred's ingress on port 8088 and Keycloak
directly on port 8080. Its pods trust the internal realm authority
`keycloak:8080`. A token requested through `localhost` has a different issuer
and is rejected even though login succeeds. Use the realm URL below, with
`keycloak` resolving to `127.0.0.1` on the workstation, as required by
fred-deployment-factory's `k3d-apps/fred/finish` for browser login too (`getent hosts keycloak` to check).

A healthy cluster and a working browser login are not sufficient. Prepare the
following once for your local integration-testing session, before running Make:

1. **Import the demo users, teams and roles** through Fred's **Admin > Migration**
   with the demo bundle described above. The harness exercises several identities
   and teams; your own administrator account cannot substitute for them.
2. **Enable password login for the test client.** Open the Keycloak admin console
   at `http://keycloak:8080`, select realm **app**, then
   `Clients > app > Settings > Capability config`. Switch **Direct access grants**
   **On** and **Save**.
   Record its previous value. The factory defaults this setting to **Off**. The
   browser uses an interactive authorization-code flow; the harness instead sends
   each demo user's credentials to the token endpoint with `grant_type=password`
   so it can test their individual permissions. Enabling this login flow does not
   grant a Fred role or bypass JWT/OpenFGA checks. No restart is required.
3. **Enable the runtime prerequisites in Fred's Admin > Features.** For
   `FRED_TEST_TEAM` (default `fredlab`), enable **Test Assistant (no LLM)**
   (`fred.github.test_assistant`), **document_access**, and the runtime's configured
   default chat model. Use the platform default or an explicit team grant, and
   record any settings you change. The default k3d model is
   `openai/mistral-small-latest` (`model__openai__mistral-small-latest`); use the
   model selected by your deployment if different. A running pod only registers
   its catalog: team access is still controlled by these grants. The runtime
   checks model access during graph-agent activation even though this diagnostic
   agent makes no chat LLM call. Document ingestion still requires working
   embeddings and a Knowledge Flow worker.

**Keep these settings enabled throughout your manual test iterations.** The Make
command neither enables them nor restores them afterward. Restore the original
Keycloak and capability/model settings when you finish the testing session, not
between commands you intend to rerun. After a fresh cluster or infrastructure
reprovisioning, check the prerequisites again. These are local test settings;
leave shared realm templates and production policy unchanged.

**Why the UI self-test can work while Make fails:** the UI uses the signed-in
browser user's token. It does not perform password-grant logins as all the demo
users. Agent, capability and model access still apply to its selected team.

| Symptom | Meaning and action |
| --- | --- |
| Many setup errors repeat `Keycloak login/refresh failed for 'alice'` and `Keycloak rejected the password grant` | The shared setup cannot log in as the demo admin. Check Direct access grants on client `app` in realm `app`. These are repeated consequences of one prerequisite failure, not separate isolation findings. |
| Login succeeds, but Fred rejects the token | Check that `FRED_REALM_URL` uses the trusted `keycloak:8080` issuer and that the host alias resolves. |
| Test Assistant unavailable or `document_access` missing | Check the runtime catalog and the test team's effective grants in Admin > Features. |
| `ModelNotUsableError` during execution | Enable the configured default chat model for the test team; the no-LLM test agent still goes through model authorization at activation. |

From the repository root, for that default local k3d installation:

```bash
# Full campaign, after the preparation above (the target selects URLs only):
make integration-test-k3d

# Focused run, with separate evidence from the full campaign:
make integration-test-k3d VALIDATION_ARGS="scenarios/test_document_access.py" \
  VALIDATION_REPORT=document-access-report.md VALIDATION_JUNIT_XML=document-access-report.xml

# Equivalent invocation of the original configurable target:
make validation-report \
  FRED_REALM_URL=http://keycloak:8080/realms/app \
  FRED_CONTROL_PLANE_URL=http://localhost:8088/control-plane/v1 \
  FRED_KNOWLEDGE_FLOW_URL=http://localhost:8088/knowledge-flow/v1 \
  FRED_RUNTIME_PUBLIC_BASE=http://localhost:8088
```

For another deployment, adapt the addresses to its trusted issuer and public
ingress. Keep TLS verification enabled. The runtime base is the public origin
resolving `prepare-execution` URLs.

The command runs the local validation code against the deployed services; it
does not rebuild or redeploy k3d. Report paths are relative to `validation/`.
Record the deployed image revision separately from the validation checkout SHA.

Limits: this exercises HTTP/runtime contracts, not the browser composer's upload
and cache-refresh sequence or a ReAct model's interpretation. OpenFGA failure
injection/retry, concurrent add/remove operations, label search and exhaustive
coverage of all document tools need separate targeted tests. The former README's
`corpus/capabilities` claims referred to a missing `test_content_scope_bypass.py`;
that endpoint's authorization matrix is still a coverage gap. No live failure
injection is performed against the shared deployment.

## Folder inventory and deletion

`scenarios/test_folder_inventory.py` covers
[#2845](https://github.com/ThalesGroup/fred/issues/2845). The tabular case uploads
one team CSV and checks that discovery (team-scoped and unscoped), description and a
SQL query all reach it. The folder case creates
three processed documents, checks the folder detail and paginated listing, then
deletes the folder. Store audit counts and the team's storage counter must first
increase by the fixture's exact contribution, then return to their baseline.
An unrelated fixture folder must survive. This requires a platform admin for
read-only store audits, the demo editor, ingestion/embeddings, and an otherwise
idle local deployment: concurrent imports/deletions invalidate the count checks.
No Test Assistant or chat model is required for this focused campaign.

This campaign does not call the label endpoints and therefore does not validate
PostgreSQL label filtering. The separate fred-core
`fred_core/tests/integration/test_postgres_document_store_sql.py` suite executes
all three label queries against a real PostgreSQL instance. SQLite service tests
cover controlled stale-write races with an OpenFGA double; those are not live
OpenFGA integration evidence.

```bash
make integration-test-k3d VALIDATION_ARGS="scenarios/test_folder_inventory.py"

# Explicitly create the large background corpora (1,001 for the folder case,
# 3,000 for the tabular case):
FRED_VALIDATION_LARGE_CORPUS=1 make integration-test-k3d \
  VALIDATION_ARGS="scenarios/test_folder_inventory.py"
```

The large cases are skipped by default. They upload the background corpus in batches
of 50 through `/upload-documents`, without scheduling embeddings for it. They then
check the small target folder, or the CSV, amid more than 1,000 readable documents. Allow time
for upload, authorization, store audits and cleanup; this is a correctness campaign,
not a latency benchmark. Use only a disposable local test deployment with sufficient
quota. The ordering of a real OpenFGA ListObjects result is not guaranteed; the
offline regression tests separately force the target documents to be omitted.

Fixture libraries have unique names and cleanup targets only their returned IDs.
Cleanup failures remain test failures. Against an older broken deployment, folder
deletion can itself orphan fixture documents; inspect the corpus audit and test
output before rerunning. This campaign does not repair historical orphans or test
storage outages, concurrent ingestion/deletion, or global discovery completeness.
