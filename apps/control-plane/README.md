# control-plane

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it. Use the [source map](src/README.md) to locate a feature.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8222/control-plane/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres, OpenFGA and Keycloak containers
make test-lifecycle-temporal          # disposable SQL/FGA/Temporal worker recovery
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## From scratch (fred-deployment-factory)

**Host run, after `make docker-up` or `make k3d-up`:**

With `DATABASE_URL` pointing to the configured control-plane database, apply
migrations explicitly before starting the API:

```sh
cargo run --locked -- migrate
make run
```

API startup only checks the installed migration history and checksums. It does
not initialize an empty database or apply pending migrations.

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app APP=fred DIR=../fred            # build, import, sync
make k3d-app-validate APP=fred DIR=../fred   # lint and render only
make k3d-logs SVC=control-plane-backend
```

Use `ENV=secondary` for this checkout's local profile. It deploys
`control-plane-backend`, `knowledge-flow-worker` and `frontend`; HTTP and background
tasks run together as `control-plane serve`. See [the profile](../../deploy/k3d/README.md).
Open Fred, sign in, accept the CGU, then enter the deployment bootstrap secret in the UI. The local service uses `FRED_BOOTSTRAP_TOKEN` from `config/.env`.
The k3d Fred values read the cluster secret `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`; use the value supplied by your deployment.

The root is platform owner and has no organization membership. Open
**Provisioning**, import the ZIP built below, then sign out and sign in as an
imported user. That person accepts their own CGU and sees their declared spaces.
There is no automatic personal space or default-team enrollment.

`app.gcu_version: v1` enables this step in the reference and k3d configurations.
Changing the version requires everyone, including root, to accept again. Publish
the corresponding frontend `gcu.<language>.md`/`gcu.md` assets with the version;
`null` disables the gate. Existing Python consent and bootstrap records are not
manager consent or bootstrap records.

## Commands

| Command | Purpose |
| --- | --- |
| `control-plane serve` | HTTP API and its background tasks (default) |
| `control-plane discover-agents` | Reads public templates from enabled configured runtimes; JSON output, no SQL or enrollment |
| `control-plane migrate` | Applies pending SQL migrations from `DATABASE_URL` |
| `control-plane generate-openapi` | Prints the HTTP contract, without configuration or services |
| `control-plane generate-config-schema` | Prints the configuration JSON Schema |
| `control-plane processing-schema` | Prints the wire contracts shared with the Knowledge Flow worker |
| `control-plane import-provisioning <bundle.zip> --token-file <path>` | Authenticated additive import ([below](#import-a-provisioning-bundle)) |

## Discover agent definitions

`control-plane discover-agents` loads the usual `ENV_FILE` and `CONFIG_FILE`,
then calls each enabled `platform.runtime_catalog_sources` entry:

```yaml
platform:
  runtime_catalog_sources:
    - runtime_id: fred-agents
      base_url: http://localhost:8000/fred/agents/v2
      enabled: true
```

From `apps/control-plane`, run `cargo run --locked -- discover-agents` after
starting fred-agents. The runtime's public `GET /agents/templates` endpoint needs
no bearer. Output is a JSON array of `{runtime_id, templates}`; template payloads
retain tuning, capability metadata and additional runtime fields. Internal
(non-public) templates are excluded. Disabled sources are not contacted; an
omitted platform configuration yields an empty array.

This operator command uses a 10-second timeout per source and exits with an error
if any source fails, without printing a partial catalog. It does not start the API,
connect to SQL/OpenFGA, persist definitions or enroll instances. `serve` does not
poll runtimes. This command does not enroll or execute agents.

## Background tasks

`control-plane serve` supervises HTTP, storage cleanup, the processing dispatcher
and configured lifecycle tasks in one process. Lifecycle is disabled by default.
See [activation and policy configuration](../../docs/architecture/A3-manager-operations.md#space-deletion-lifecycle).

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Applied SQL migrations are
immutable, including comments and whitespace. Add the next numbered SQL file under
`migrations/` for each schema change; preserve existing data
(see [Existing local state](#existing-local-state)).

## Generate the frontend contract

```sh
make generate-openapi                       # writes ignored openapi.json
make -C ../frontend update-control-plane-api  # regenerates schema, RTK endpoints and types
```

Generation runs without configuration, credentials or services. The frontend's
`update-all-apis` includes control-plane. Commit the regenerated
`src/slices/controlPlane/controlPlaneOpenApi.ts` with changes to routes or DTOs;
never edit it by hand. The slice uses the shared bearer/refresh base query and
Redux store. Its enhancement encodes the generated import argument as multipart
FormData, retaining the generated URL, method and completed-report type.
Bootstrap and import never retry automatically on 401; expiry can follow committed effects.
Frontend consumers use `controlPlaneApiEnhancements`. Background tasks establish
their Temporal connections independently of HTTP serving.

## Platform and space roles

`GET /me` reports effective platform roles. Platform owners list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Any platform owner names or
removes other owners; the last one cannot be revoked. `platform_observer`,
`feature_manager` and `prompt_editor` are also supported.

Owner is technical: on the platform, and on each organization, where it names the
organization's admins and reads nothing. Platform owners name organization owners.
Space roles `member`, `editor`, `analyst` and `admin` are business roles. They are
cumulative; admin alone does not read content. Editor, admin and analyst also apply
to every descendant space; member stays local, and a personal space inherits nothing.
Organization admins create teams, team admins create projects. The last admin of a
non-personal space, and the last owner of an organization, cannot be revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/A1-manager-runtime.md#platform-administration-and-self-checks).

Organizations are created through the platform form (`POST /control-plane/v1/admin/organizations`)
or a provisioning ZIP. Without the frontend, use the authenticated HTTP endpoint or
`make import-provisioning BUNDLE=<zip> TOKEN_FILE=<bearer-file>` on an initialized
installation. Both paths require a platform owner; creation does not restore a lost
platform-owner role.

Platform grants and organization-owner grants require the manager's service client. The factory
provisions the `control-plane` client and its directory grants. The cluster uses
`KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` from `fred-secrets`. To reuse that identity
on the host, set `security.m2m.client_id` to `control-plane`, set its
`secret_env_var` to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, and supply that secret
in the host `.env`.
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

After compatible initialization, personal CGU acceptance and root bootstrap, save a platform owner's
access token in a private file and run:

```sh
make import-provisioning BUNDLE=target/demo-provisioning-bundle.zip TOKEN_FILE=/path/to/operator-token
# Equivalent binary command:
control-plane import-provisioning /path/to/bundle.zip --token-file /path/to/operator-token
```

The CLI uses the normal configuration and the manager's Keycloak service client.
It needs neither the running HTTP server nor Temporal and never initializes or
migrates SQL/OpenFGA. The HTTP equivalent is multipart
`POST /control-plane/v1/import-export/import`, with exactly one field named `file`
and the operator bearer. It checks platform ownership before reading the upload.
A new organization declares at least one owner and one admin. Archive limits are 50 MiB compressed and
100 MiB expanded, with no filesystem extraction.

Existing identities keep their profile and password; new identities need a
nonempty password. Usernames must already be lowercase, without surrounding
whitespace or control characters. Noncanonical names and known new-user email
conflicts are rejected before any provisioning writes. All space roles are explicit: admin alone grants no content
access, and every child-role holder needs a direct parent content role. Replay
preserves committed space IDs and undeclared grants and repairs requested grants.
Success returns JSON counts only after completion. A failed run reports a safe
phase and acknowledgment counts; correct the cause and replay with a valid token.
There is no cross-system rollback, so failure does not prove absence of effects.

`make test-integration` imports the actual Make artifact over HTTP with disposable
Keycloak, PostgreSQL and OpenFGA, verifies replay and identity preservation, and
imports a variant with a project.

## Import through the frontend

Fred's existing administration console exposes **Provisioning** at
`/admin/provisioning` to manager platform owners. Select the ZIP produced by `make build-demo-bundle`.
The page displays the completed server counts or an error with explicit replay
guidance. The existing Home and sidebar display own memberships, hierarchy and roles.
The account menu permits logout before and after admission. Platform owners are restricted to governance/account routes. Business users retain
the existing product UI; endpoints not yet reconstructed can fail.

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
consent isolation, empty root memberships, persisted hierarchy/roles, reports,
refusals, unsupported direct URLs and keyboard logout through the existing account
menu. Any control-plane, knowledge-flow or agent-runtime call fails the test. Screenshots are
written under the frontend's ignored `target/` directory. The manager's
`make test-browser` invokes the same journey and integration suite when frontend
dependencies and Chromium are already installed.

## Existing local state

The architecture dossier contains the [SQL table catalogue](../../docs/architecture/A2-manager-contracts.md#control-plane-sql-catalogue)
and [SQLx operations](../../docs/architecture/A3-manager-operations.md#sqlx-schema-evolution).

SQLx records applied versions and checksums in `_sqlx_migrations`. Before upgrading,
inspect that history and back up the database. The `control-plane migrate` command
applies pending SQL files. API startup only verifies that the migration history
matches the binary's embedded versions and checksums, and refuses an incompatible
or uninitialized database. The k3d factory profile enables the chart's
pre-install/pre-upgrade migration Job. Rebuilding the Rust
image embeds new migration files; no manual SQL command is needed for this upgrade.

`0001_manager_schema.sql` creates the initial schema; later numbered files evolve it.
A database whose recorded
versions or checksums differ from the embedded files is refused by the API and by
`migrate`; recreate it explicitly. Do not edit applied files or replace stored checksums.

The OpenFGA model still follows its separate pre-release replacement policy.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md#authorization-store-publication)
describes publication and retry rules.

A role mutation that loses its authorization revision returns a conflict; replay
rechecks current authority. Timeout is not rollback. Roles and permission evaluation
remain in OpenFGA; SQL holds only the active store/model binding.

## Existing environment identifiers

The service and binary are named `control-plane`; the image remains
`control-plane-backend`. The current defaults use OpenFGA store `control-plane`
and lifecycle queue/prefix `control-plane-lifecycle`. Existing persisted resources
are not renamed or migrated by deployment. These defaults require a fresh
secondary installation or an explicit migration of existing state; application
reset is not supported for the Rust ingestion profile.

The frontend's `controlPlane` client targets this Rust API. `legacyControlPlane`
retains the previous API types and clients for screens not yet migrated; the
Python backend is no longer shipped.

### Document search inclusion

`Document.retrievable` is the last confirmed inclusion state, separate from processing
success and caller permissions. Publication reads and verifies `metadata.json` before
persisting it in the same transaction as the final manifest. The vector worker checks
the flag on written chunks. Existing listing and content permissions are unchanged.

`PUT /documents/{id}/retrievable` with `{"retrievable": false}` or `true` requires the
existing space write permission and a published vector generation. KF updates only
its published chunk IDs and reads them back before confirming SQL. The response is
200 only after confirmation. `retrievable_pending` drives the existing UI refresh;
503 means the outcome is not confirmed, not that the operation was rolled back.
Repeating an already confirmed request returns its durable result without delivery or
mutation. While pending, the same actor can repeat the same request; an opposite
request is rejected. The command and its phase live in `document.retrieval_command`:

- `ready`: the worker must atomically claim `writing` before touching OpenSearch.
  Only one claim succeeds, including after an API restart or Temporal history expiry.
- `writing`: the mutation activity has one attempt. Its timeout, termination or
  partial failure never authorizes another writer. A lost claim response also stays
  protected, even if no write actually began.
- `applied`: a separate activity records successful writer completion. That callback
  retries independently, without an overall workflow deadline, so a temporary SQL/HTTP
  outage does not discard Temporal's evidence that the writer returned. Verification
  and confirmation then run in a separate activity (up to five attempts per run).
- `confirmed=true`: SQL contains the verified value; duplicate confirmations are
  idempotent. Every callback is fenced by the current operation ID.

Delivery uses `ALLOW_DUPLICATE_FAILED_ONLY`, with `FAIL` on a running ID and a fresh
start-request ID. A failed, timed-out, cancelled or terminated run may restart; it
reads the persisted phase and never repeats a claimed mutation. `AlreadyExists` is
described and accepted only for a running execution, not a closed failure. A completed
run is not restarted. These policies follow the
[Temporal workflow identity contract](https://docs.temporal.io/workflow-execution/workflowid-runid).

For diagnosis, use the authenticated internal GET
`/document-processing/retrievable/{id}?operation_id={operation_id}` and the matching
`manager-retrievable-{installation}-{operation_id}` Temporal history. If the phase is
`applied`, repeat the original PUT to retry verification/confirmation. If it is
`writing`, inspect whether the completion-recording activity is still retrying; it
can finish without reapplying the mutation. A closed run with `writing`, a partial
projection, or an old command without a phase (`uncertain`) requires investigation
of the activity and remote write. There is **no automatic repair or operator reset
endpoint** for that case. Keep pending, do not clear the command or submit the opposite
value; any repair must first establish that the old writer and remote operations
have stopped and be separately scoped. A read matching the target alone is not proof
that an uncertain writer has stopped.

OpenSearch verifies exactly the IDs derived from `manifest.vector_ordinals` with
sequential `_mget` batches of at most 500. Only `metadata.document_uid` and
`metadata.retrievable` are requested. Missing/duplicate/unexpected IDs, per-item errors,
wrong ownership and nonmatching boolean values reject confirmation. For N published
chunks and batch size B=500, each verification pass costs `ceil(N/B)` requests (zero
for N=0), with at most one in flight, instead of N full-chunk reads. A confirmation
retry before SQL succeeds can repeat this read cost; a confirmed replay performs no
vector reads. No latency or throughput measurement is claimed. Unsupported vector
backends explicitly reject both generation-scoped mutation and verification.

Migration `0004_document_retrievable.sql` adds state without adopting pre-existing
vector data. Before considering an old document's indicator repaired, an authorized
writer must explicitly call the same route with `{"retrievable": null}`. This restores
only a document with no prior inclusion command, using the verified published
metadata and checking every published chunk; it does not rewrite vectors or ingest
again. A mismatch fails instead of guessing from counts. Apply it per selected ID,
not as an automatic startup sweep. This action was prepared but not run for the
reported PDF. The manager index remains isolated from legacy search/chat.
