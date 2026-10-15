# fred-manager

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8400/fred-manager/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres, OpenFGA and Keycloak containers
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## From scratch (fred-deployment-factory)

**Host run, after `make docker-up` or `make k3d-up`:**

```
make run
```

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app DIR=../fred/apps/fred-manager            # build, import, sync
make k3d-app-validate DIR=../fred/apps/fred-manager   # lint and render only
make k3d-logs SVC=fred-manager
make k3d-app-uninstall DIR=../fred/apps/fred-manager
```

Deploy the frontend from this branch as well. Open Fred, sign in with your own
Keycloak account, read and accept the CGU, then enter the deployment bootstrap
secret in the UI. The local service uses `FRED_BOOTSTRAP_TOKEN` from `config/.env`.
The k3d manager overlay reads the cluster secret `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`; use the value supplied by your deployment.

The root has platform authority and no organization membership. Open
**Provisioning**, import the ZIP built below, then sign out and sign in as an
imported user. That person accepts their own CGU and sees their declared spaces.
There is no automatic personal space or default-team enrollment.

`app.gcu_version: v1` enables this step in the reference and k3d configurations.
Changing the version requires everyone, including root, to accept again. Publish
the corresponding frontend `gcu.<language>.md`/`gcu.md` assets with the version;
`null` disables the gate. Existing Python consent and bootstrap records are not
manager consent or bootstrap records.

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Applied migrations are never
edited; add a new one.

## Generate the frontend contract

```sh
make generate-openapi                       # writes ignored openapi.json
make -C ../frontend update-fred-manager-api  # regenerates schema, RTK endpoints and types
```

Generation runs without configuration, credentials or services. The frontend's
`update-all-apis` includes fred-manager. Commit the regenerated
`src/slices/fredManager/fredManagerOpenApi.ts` with changes to routes or DTOs;
never edit it by hand. The slice uses the shared bearer/refresh base query and
Redux store. Its enhancement encodes the generated import argument as multipart
FormData, retaining the generated URL, method and completed-report type.
Bootstrap and import never retry automatically on 401; expiry can follow committed effects.
The generation target also corrects the code generator's required-body typing for
the optional ingestion request. Frontend consumers use `fredManagerApiEnhancements`.

## Platform and space roles

`GET /me` reports effective platform roles. Platform administrators list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Only the bootstrap root changes
`platform_admin`; its own grant is protected. `platform_observer`, `team_manager`,
`feature_manager` and `prompt_editor` are also supported.

Space roles are `member`, `editor`, `analyst` and `admin`. They are cumulative;
admin alone does not read content. The last admin of a non-personal space cannot be
revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/A1-manager-runtime.md#platform-administration-and-self-checks).

Directory-backed platform grants require the manager's service client. The factory
consumes `deploy/k3d/identities.yaml` during `k3d-app`; copy its generated
`KEYCLOAK_FRED_MANAGER_CLIENT_SECRET` from `fred-secrets` to the host `.env` when
running locally against that realm. `docker-up` alone does not provision this client.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md) describes configuration.

## Import a provisioning bundle

Build the checked-in demo, without running services:

```sh
make build-demo-bundle
# Optional overrides, with the same names as control-plane:
make build-demo-bundle DEMO_PROVISIONING_FIXTURE_DIR="/path/to/fixtures" DEMO_BUNDLE_FILE="/path/to/demo.zip"
```

The ZIP contains exactly `manifest.json`, `users.json`, `organizations.json`,
`teams.json` and `projects.json`. The manifest declares `format_version: 2`,
`users_schema_version: 2`, `source_platform: "swift"`. The four data files are arrays.
The demo contains 15 identities, one organization, three teams and an empty project
array. Demo passwords are test credentials. The
[declaration contract](../../docs/architecture/A2-manager-contracts.md#provisioning-declarations)
defines explicit parent references and roles, including projects. Old JSON and
Python version-1 ZIPs return `not_yet_supported`; no conversion is performed.

After compatible initialization, personal CGU acceptance and root bootstrap, save a platform administrator's
access token in a private file and run:

```sh
make import-provisioning BUNDLE=target/demo-provisioning-bundle.zip TOKEN_FILE=/path/to/operator-token
# Equivalent binary command:
fred-manager import-provisioning /path/to/bundle.zip --token-file /path/to/operator-token
```

The CLI uses the normal configuration and the manager's Keycloak service client.
It needs neither the running HTTP server nor Temporal and never initializes or
migrates SQL/OpenFGA. The HTTP equivalent is multipart
`POST /fred-manager/v1/import-export/import`, with exactly one field named `file`
and the operator bearer. It checks platform authority before reading the upload.
A bundle declaring platform admin requires the bootstrap root, even on replay;
the demo includes such a declaration. Archive limits are 50 MiB compressed and
100 MiB expanded, with no filesystem extraction.

Existing identities keep their profile and password; new identities need a
nonempty password. All space roles are explicit: admin alone grants no content
access, and every child-role holder needs parent content membership. Replay
preserves committed space IDs and undeclared grants and repairs requested grants.
Success returns JSON counts only after completion. A failed run reports a safe
phase and acknowledgment counts; correct the cause and replay with a valid token.
There is no cross-system rollback, so failure does not prove absence of effects.

`make test-integration` imports the actual Make artifact over HTTP with disposable
Keycloak, PostgreSQL and OpenFGA, verifies replay and identity preservation, and
imports a variant with a project.

## Import through the frontend

The experimental manager entry exposes **Provisioning** at `/admin/provisioning` to
manager platform administrators. Select the ZIP produced by `make build-demo-bundle`.
The page displays the completed server counts or an error with explicit replay
guidance. The demo declares a platform admin and therefore requires the bootstrap
root. The entry mounts only onboarding, own memberships and provisioning; legacy
control-plane pages are not part of this journey.

From `apps/frontend`, automate this journey without touching development data:

```sh
make install-test-browser       # once: Chromium, after installing Node dependencies
make test-provisioning-browser
```

The test needs Docker, Node/npm and the Rust/protoc prerequisites above. It starts
throwaway PostgreSQL, OpenFGA and Keycloak plus the real manager governance router
and Vite frontend, then removes its services. Starting with no root or consent,
it accepts CGU, bootstraps through the UI, imports the actual Make ZIP, replays it,
imports a project variant, then switches accounts in the same browser. It checks
consent isolation, empty root memberships, persisted hierarchy/roles, reports and
refusals. Any control-plane or knowledge-flow call fails the test. Screenshots are
written under the frontend's ignored `target/` directory. The manager's
`make test-browser` invokes the same journey and integration suite when frontend
dependencies and Chromium are already installed.

## Upgrade existing authorization

Stop legacy manager writers and settle pending requests, then run
`make migrate-authorization` with the normal operator configuration. Existing
nonempty installations refuse automatic cutover during `serve`. The command
preserves supported roles, permissions, space IDs and bootstrap state in a fresh
OpenFGA store and publishes its IDs in SQL; replay never recopies a published store.
Invalid legacy models, hierarchy or grants require repair before cutover. The
[deployment chapter](../../docs/architecture/A3-manager-operations.md#offline-authorization-cutover)
defines the offline precondition and failure behavior.

A role mutation that loses its authorization revision returns a conflict; replay
rechecks current authority. Timeout is not rollback. Roles and permission evaluation
remain in OpenFGA; SQL holds only the active store/model binding.
